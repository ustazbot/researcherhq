import uuid
import json
import hashlib
import struct
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import app.database as _db_module
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user
from app.services.embedding_pool import embedding_pool
from app.services.rag_pipeline import retrieve_chunks, cosine_similarity
from app.services.llm_provider import query_llm, KREDIT_COST
from app.services.web_search_service import search_with_citations, WebSearchUnavailable

logger = logging.getLogger(__name__)

router = APIRouter()


def deduct_credits(db, user_id: str, cost: int) -> int:
    """Deduct from kredit_subscription first, then kredit_topup. Returns new kredit_remaining."""
    row = db.execute(
        "SELECT kredit_subscription, kredit_topup FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    sub, top = row["kredit_subscription"], row["kredit_topup"]
    if sub >= cost:
        new_sub, new_top = sub - cost, top
    elif sub + top >= cost:
        new_sub, new_top = 0, top - (cost - sub)
    else:
        raise ValueError("Insufficient credits")
    db.execute(
        """UPDATE users
           SET kredit_subscription = ?, kredit_topup = ?, kredit_remaining = ?
           WHERE id = ?""",
        (new_sub, new_top, new_sub + new_top, user_id)
    )
    return new_sub + new_top

OUTPUT_MODES = {"qa", "literature_review", "executive_summary", "key_findings", "research_gap", "discovery", "proposal_extract"}
PRO_ONLY_MODES = {"literature_review", "executive_summary", "research_gap"}

NEAR_MATCH_THRESHOLD = 0.95


def _build_project_context(project: dict) -> str:
    DEGREE_LABEL = {
        "master": "Master",
        "phd": "Doktor Falsafah (PhD)",
        "lain-lain": "Lain-lain",
    }
    MODE_LABEL = {
        "general": "Umum",
        "quantitative": "Kuantitatif",
        "qualitative": "Kualitatif",
        "law": "Undang-undang",
        "medicine": "Perubatan/Sains Kesihatan",
    }
    lines = []
    if project.get("degree_level"):
        lines.append(f"Peringkat: {DEGREE_LABEL.get(project['degree_level'], project['degree_level'])}")
    if project.get("field"):
        lines.append(f"Bidang: {project['field']}")
    if project.get("title"):
        lines.append(f"Tajuk kajian: {project['title']}")
    if project.get("citation_style"):
        lines.append(f"Gaya citation: {project['citation_style']}")
    return "\n".join(lines) if lines else ""


async def _handle_no_document_query(
    query: str, research_mode: str, style_notes: str,
    project_context: str = "", chat_language: str = "bm", output_language: str = "bm"
):
    """Route no-document queries to llm_knowledge fallback (web search is explicit toggle now)."""
    no_doc_prefix = (
        "[SITUASI: Pengguna belum muat naik sebarang dokumen dalam projek ini. "
        "Jawab soalan mereka secara umum (LLM_GENERAL mode) dengan label [💬 Jawapan Umum]. "
        "Di akhir jawapan, WAJIB cadangkan: cari artikel melalui Search Panel atau muat naik dokumen.]\n\n"
    )
    result = await query_llm(
        messages=[{
            "role": "user",
            "content": no_doc_prefix + f"Soalan: {query}",
        }],
        research_mode=research_mode,
        output_mode="qa",
        style_notes=style_notes,
        project_context=project_context,
        chat_language=chat_language,
        output_language=output_language,
    )
    return "llm_knowledge", result["content"], []


def _assess_chunk_relevance(chunks: list, scores: list) -> str:
    """Returns: 'none' | 'low' | 'good'"""
    if not chunks or not scores:
        return "none"
    avg_score = sum(scores) / len(scores)
    if avg_score < 0.35:
        return "low"
    return "good"


def normalize_query(query: str) -> str:
    return " ".join(query.lower().strip().split())


def _cache_key(query: str, project_id: str, doc_version: int) -> str:
    raw = f"{normalize_query(query)}|{project_id}|{doc_version}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _emb_to_blob(emb: list) -> bytes:
    return struct.pack(f"{len(emb)}f", *emb)


def _blob_to_emb(blob: bytes) -> list:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


def _check_cache(project_id: str, query: str, query_embedding: list, doc_version: int, db):
    key = _cache_key(query, project_id, doc_version)
    # Exact match
    cached = db.execute(
        "SELECT response, source_chunks FROM query_cache WHERE id = ? AND document_set_version = ?",
        (key, doc_version),
    ).fetchone()
    if cached:
        return cached

    # Near-match: cosine similarity > 0.95
    recent = db.execute(
        "SELECT query_embedding, response, source_chunks FROM query_cache WHERE project_id = ? AND document_set_version = ?",
        (project_id, doc_version),
    ).fetchmany(50)
    for row in recent:
        if row["query_embedding"]:
            stored_emb = _blob_to_emb(row["query_embedding"])
            if cosine_similarity(query_embedding, stored_emb) > NEAR_MATCH_THRESHOLD:
                return row

    return None


def _store_cache(key: str, project_id: str, query: str, query_embedding: list,
                 doc_version: int, response: str, source_chunks: list, db):
    db.execute(
        """INSERT OR REPLACE INTO query_cache
           (id, project_id, query_normalized, query_embedding, document_set_version,
            response, source_chunks, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            key, project_id, normalize_query(query),
            _emb_to_blob(query_embedding),
            doc_version, response,
            json.dumps([c["chunk_id"] for c in source_chunks]),
            datetime.utcnow().isoformat(),
        ),
    )

def _get_voice_style(project_id: str, db) -> str:
    """Return style_notes for this project, or '' if none."""
    row = db.execute(
        "SELECT style_notes FROM voice_profile WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    return row["style_notes"] if row else ""


class QueryRequest(BaseModel):
    query: str
    output_mode: str = "qa"
    query_type: str = "normal"  # "normal" | "deep"

@router.post("/{project_id}/query")
async def query_project(
    project_id: str,
    body: QueryRequest,
    user=Depends(get_current_user),
):
    if body.output_mode not in OUTPUT_MODES:
        raise HTTPException(400, f"Output mode tidak sah: {body.output_mode}")

    with get_db() as db:
        proj = db.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"]),
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")

        user_row = db.execute(
            "SELECT kredit_remaining, tier, chat_language FROM users WHERE id = ?",
            (user["user_id"],),
        ).fetchone()

        tier = user_row["tier"]
        chat_language = user_row["chat_language"] if user_row["chat_language"] else "bm"
        output_language = proj["output_language"] if proj["output_language"] else "bm"
        # ponytail: server-side only — client cannot influence this via request fields
        is_discovery_lite = (body.output_mode == "discovery" and tier != "pro")

        if body.output_mode in PRO_ONLY_MODES and tier != "pro":
            raise HTTPException(403, "Mod ini hanya untuk pengguna Pro.")

        mode_key = "qa_deep" if (body.query_type == "deep" and body.output_mode == "qa") else body.output_mode
        kredit_cost = KREDIT_COST.get(mode_key, 1)

        if user_row["kredit_remaining"] < kredit_cost:
            raise HTTPException(402, "Kredit Kajian tidak mencukupi.")

        project_dict = dict(proj)
        project_context = _build_project_context(project_dict)

    # Embed query
    query_embedding = await embedding_pool.embed(body.query)

    # Cache check — before LLM call (free hit)
    with get_db() as db:
        doc_version = db.execute(
            "SELECT document_set_version FROM projects WHERE id = ?", (project_id,)
        ).fetchone()["document_set_version"]
        cached = _check_cache(project_id, body.query, query_embedding, doc_version, db)

    if cached:
        logger.info("cache_hit project=%s", project_id)
        return {
            "answer": cached["response"],
            "sources": json.loads(cached["source_chunks"] or "[]"),
            "web_citations": [],
            "source_type": "rag_document",
            "kredit_used": 0,
            "kredit_remaining": user_row["kredit_remaining"],
            "cache_hit": True,
        }

    logger.info("cache_miss project=%s", project_id)
    with get_db() as db:
        style_notes = _get_voice_style(project_id, db)

    # Retrieve relevant chunks
    chunks = await retrieve_chunks(
        project_id=project_id,
        query_embedding=query_embedding,
        query_type=body.query_type,
        db_path=_db_module._db_path,
    )

    scores = [c.get("similarity", 0) for c in chunks]
    relevance = _assess_chunk_relevance(chunks, scores)

    if relevance == "none":
        source_type, answer, web_citations = await _handle_no_document_query(
            query=body.query,
            research_mode=project_dict["research_mode"],
            style_notes=style_notes,
            project_context=project_context,
            chat_language=chat_language,
            output_language=output_language,
        )
        kredit_cost = 1
        with get_db() as db:
            new_kredit = deduct_credits(db, user["user_id"], kredit_cost)
            msg_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            db.execute(
                """INSERT INTO messages (id, project_id, role, content, output_mode, source_chunks, kredit_used, tokens_used_internal, created_at)
                   VALUES (?, ?, 'assistant', ?, ?, '[]', ?, 0, ?)""",
                (msg_id, project_id, answer, body.output_mode, kredit_cost, now),
            )
        return {
            "answer": answer,
            "sources": [],
            "web_citations": web_citations,
            "source_type": source_type,
            "kredit_used": kredit_cost,
            "kredit_remaining": new_kredit,
        }

    # Build context from chunks
    context_parts = []
    for i, chunk in enumerate(chunks, start=1):
        context_parts.append(
            f"[Sumber {i}: {chunk['filename']}, ms. {chunk['page_number']}]\n{chunk['text']}"
        )
    context = "\n\n---\n\n".join(context_parts)

    # Add hierarchical context for cross-chapter modes
    if body.output_mode in ("literature_review", "research_gap"):
        with get_db() as db:
            summaries = db.execute("""
                SELECT ch.title, cc.summary
                FROM chapters ch
                JOIN chapter_content cc ON ch.id = cc.chapter_id
                WHERE ch.project_id = ? AND cc.summary != ''
                ORDER BY ch.chapter_order
            """, (project_id,)).fetchall()
        if summaries:
            summary_context = "\n\n".join(
                f"[Ringkasan {row['title']}]: {row['summary']}" for row in summaries
            )
            context = f"RINGKASAN BAB SEDIA ADA:\n{summary_context}\n\n---\n\n" + context

    # Tier-gated discovery lite — determined server-side from DB tier, never from client input
    effective_query = body.query
    if is_discovery_lite:
        effective_query = f"[MODE LITE AKTIF — hanya langkah 1-2, output nota ringkas]\n\n{body.query}"

    # For discovery mode: load conversation history so AI can track which step we're on
    history_messages = []
    if body.output_mode == "discovery":
        with get_db() as db:
            history_rows = db.execute(
                """SELECT role, content FROM messages
                   WHERE project_id = ? AND output_mode = 'discovery'
                   ORDER BY created_at ASC LIMIT 20""",
                (project_id,)
            ).fetchall()
        history_messages = [{"role": r["role"], "content": r["content"]} for r in history_rows]

    low_rel_prefix = ""
    if relevance == "low":
        low_rel_prefix = (
            "[KONTEKS: Dokumen yang ada mungkin tidak merangkumi topik ini secara mendalam. "
            "Jawab berdasarkan chunk yang ada, tapi maklumkan user bahawa sumber mungkin terhad. "
            "Tambah nota ringkas di akhir jawapan: sumber terhad, cadang tambah artikel yang lebih relevan.]\n\n"
        )

    current_message = {
        "role": "user",
        "content": low_rel_prefix + f"KONTEKS DOKUMEN:\n\n{context}\n\n---\n\nSOALAN: {effective_query}",
    }
    messages = history_messages + [current_message]

    result = await query_llm(
        messages=messages,
        research_mode=project_dict["research_mode"],
        output_mode=body.output_mode,
        query_type=body.query_type,
        style_notes=style_notes,
        project_context=project_context,
        chat_language=chat_language,
        output_language=output_language,
    )

    # Store response in cache for future hits
    cache_key_val = _cache_key(body.query, project_id, doc_version)
    with get_db() as db:
        _store_cache(cache_key_val, project_id, body.query, query_embedding,
                     doc_version, result["content"], chunks, db)

    # Deduct kredit, save message, log interaction
    with get_db() as db:
        # Re-check kredit inside the write transaction to guard race condition
        fresh = db.execute(
            "SELECT kredit_remaining FROM users WHERE id = ?", (user["user_id"],)
        ).fetchone()
        if not fresh or fresh["kredit_remaining"] < kredit_cost:
            raise HTTPException(402, "Kredit Kajian tidak mencukupi.")
        new_kredit = deduct_credits(db, user["user_id"], kredit_cost)
        db.execute(
            "UPDATE users SET tokens_used_internal = tokens_used_internal + ? WHERE id = ?",
            (result["tokens_used"], user["user_id"]),
        )
        now = datetime.utcnow().isoformat()
        # Save user message for discovery mode (enables multi-turn history)
        if body.output_mode == "discovery":
            db.execute(
                """INSERT INTO messages
                   (id, project_id, role, content, output_mode, source_chunks,
                    kredit_used, tokens_used_internal, created_at)
                   VALUES (?, ?, 'user', ?, ?, ?, 0, 0, ?)""",
                (
                    str(uuid.uuid4()), project_id, body.query, body.output_mode,
                    json.dumps([]), now,
                ),
            )
        msg_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO messages
               (id, project_id, role, content, output_mode, source_chunks,
                kredit_used, tokens_used_internal, created_at)
               VALUES (?, ?, 'assistant', ?, ?, ?, ?, ?, ?)""",
            (
                msg_id, project_id, result["content"], body.output_mode,
                json.dumps([c["chunk_id"] for c in chunks]),
                kredit_cost, result["tokens_used"], now,
            ),
        )
        db.execute(
            """INSERT INTO user_interactions
               (id, user_id, event_type, research_mode, output_mode,
                kredit_used, query_length, created_at)
               VALUES (?, ?, 'query', ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()), user["user_id"],
                project_dict["research_mode"], body.output_mode,
                kredit_cost, len(body.query), datetime.utcnow().isoformat(),
            ),
        )

    return {
        "answer": result["content"],
        "sources": [
            {
                "chunk_id": c["chunk_id"],
                "filename": c["filename"],
                "page_number": c["page_number"],
                "text_preview": c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"],
                "similarity": round(c["similarity"], 3),
            }
            for c in chunks
        ],
        "web_citations": [],
        "source_type": "rag_document",
        "kredit_used": kredit_cost,
        "kredit_remaining": user_row["kredit_remaining"] - kredit_cost,
    }

@router.get("/{project_id}/messages")
def get_messages(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"]),
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        msgs = db.execute(
            "SELECT * FROM messages WHERE project_id = ? ORDER BY created_at ASC",
            (project_id,),
        ).fetchall()
    return [dict(m) for m in msgs]
