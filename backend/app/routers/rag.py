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


WEB_SEARCH_CREDIT_COST = 5
RECENT_KEEP = 10
SUMMARY_TRIGGER = 20


class QueryRequest(BaseModel):
    query: str
    output_mode: str = "qa"
    query_type: str = "normal"  # "normal" | "deep"
    use_web_search: bool = False
    session_id: str | None = None

async def _summarize_old_messages(messages: list, project_context: str = "") -> str:
    from app.services.llm_provider import call_deepseek_raw
    history_text = "\n".join(
        f"[{m['role'].upper()}]: {m['content'][:500]}" for m in messages
    )
    prompt = (
        f"Ringkaskan perbualan akademik berikut dalam 150-200 patah perkataan. "
        f"Fokus pada: topik utama yang dibincangkan, keputusan atau dapatan penting, "
        f"konteks yang perlu diingat untuk perbualan seterusnya.\n\n"
        f"KONTEKS PROJEK:\n{project_context}\n\n"
        f"PERBUALAN:\n{history_text}\n\nRINGKASAN:"
    )
    summary = await call_deepseek_raw(prompt, max_tokens=300)
    return summary.strip()


async def build_session_history(session_id: str, project_context: str, db) -> list:
    all_msgs = db.execute("""
        SELECT role, content FROM messages
        WHERE session_id = ? AND role IN ('user', 'assistant')
        ORDER BY created_at ASC
    """, (session_id,)).fetchall()

    total = len(all_msgs)
    if total <= RECENT_KEEP:
        return [{"role": m["role"], "content": m["content"]} for m in all_msgs]

    recent = all_msgs[-RECENT_KEEP:]
    if total <= SUMMARY_TRIGGER:
        return [{"role": m["role"], "content": m["content"]} for m in recent]

    sess = db.execute(
        "SELECT conversation_summary FROM chat_sessions WHERE id = ?", (session_id,)
    ).fetchone()

    if sess and sess["conversation_summary"]:
        summary_text = sess["conversation_summary"]
    else:
        old_msgs = all_msgs[:-RECENT_KEEP]
        summary_text = await _summarize_old_messages(
            [{"role": m["role"], "content": m["content"]} for m in old_msgs],
            project_context
        )
        db.execute(
            "UPDATE chat_sessions SET conversation_summary = ? WHERE id = ?",
            (summary_text, session_id)
        )

    return [
        {"role": "system", "content": f"[RINGKASAN PERBUALAN SEBELUM INI]\n{summary_text}"},
        *[{"role": m["role"], "content": m["content"]} for m in recent]
    ]


async def _auto_title_session(session_id: str, first_query: str):
    from app.services.llm_provider import call_deepseek_raw
    prompt = (
        f"Jana tajuk ringkas (3-5 patah perkataan) untuk sesi chat akademik "
        f"berdasarkan soalan pertama ini. Tiada tanda baca. Hanya tajuk.\n\n"
        f"Soalan: {first_query[:200]}\n\nTajuk:"
    )
    try:
        title = await call_deepseek_raw(prompt, max_tokens=20)
        title = title.strip().strip('"').strip("'")[:80]
        if title:
            now = datetime.utcnow().isoformat()
            with get_db() as db:
                db.execute(
                    "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
                    (title, now, session_id)
                )
    except Exception:
        pass  # silent fail — default title kekal


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

    # Resolve active session
    with get_db() as db:
        if body.session_id:
            sess = db.execute(
                "SELECT id FROM chat_sessions WHERE id = ? AND project_id = ?",
                (body.session_id, project_id)
            ).fetchone()
            if not sess:
                raise HTTPException(404, "Sesi tidak dijumpai.")
            active_session_id = body.session_id
        else:
            latest = db.execute("""
                SELECT id FROM chat_sessions
                WHERE project_id = ?
                ORDER BY updated_at DESC LIMIT 1
            """, (project_id,)).fetchone()
            if not latest:
                active_session_id = str(uuid.uuid4())
                now_s = datetime.utcnow().isoformat()
                db.execute("""
                    INSERT INTO chat_sessions (id, project_id, title, created_at, updated_at)
                    VALUES (?, ?, 'Chat Baru', ?, ?)
                """, (active_session_id, project_id, now_s, now_s))
            else:
                active_session_id = latest["id"]

    # Web search — explicit Pro-only path, independent of RAG pipeline
    if body.use_web_search:
        if tier != "pro":
            raise HTTPException(403, "Carian web hanya untuk pengguna Pro.")
        if not settings.perplexity_api_key:
            raise HTTPException(503, "Carian web tidak tersedia pada masa ini.")
        if user_row["kredit_remaining"] < WEB_SEARCH_CREDIT_COST:
            raise HTTPException(402, f"Kredit tidak mencukupi untuk carian web. Diperlukan: {WEB_SEARCH_CREDIT_COST} kredit.")
        try:
            web_result = await search_with_citations(body.query)
            with get_db() as db:
                new_kredit = deduct_credits(db, user["user_id"], WEB_SEARCH_CREDIT_COST)
                msg_id = str(uuid.uuid4())
                now = datetime.utcnow().isoformat()
                db.execute(
                    """INSERT INTO messages (id, project_id, session_id, role, content, output_mode,
                       source_chunks, kredit_used, tokens_used_internal, created_at)
                       VALUES (?, ?, ?, 'assistant', ?, ?, '[]', ?, 0, ?)""",
                    (msg_id, project_id, active_session_id, web_result["answer"], body.output_mode, WEB_SEARCH_CREDIT_COST, now),
                )
                db.execute(
                    "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                    (now, active_session_id)
                )
            return {
                "answer": web_result["answer"],
                "sources": [],
                "web_citations": web_result["citations"],
                "source_type": "web_search",
                "kredit_used": WEB_SEARCH_CREDIT_COST,
                "kredit_remaining": new_kredit,
            }
        except WebSearchUnavailable as e:
            raise HTTPException(503, f"Carian web gagal: {str(e)}")

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
                """INSERT INTO messages (id, project_id, session_id, role, content, output_mode,
                   source_chunks, kredit_used, tokens_used_internal, created_at)
                   VALUES (?, ?, ?, 'assistant', ?, ?, '[]', ?, 0, ?)""",
                (msg_id, project_id, active_session_id, answer, body.output_mode, kredit_cost, now),
            )
            db.execute(
                "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
                (now, active_session_id)
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

    # Load session history with progressive summarization
    with get_db() as db:
        history_messages = await build_session_history(
            session_id=active_session_id,
            project_context=project_context,
            db=db,
        )

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
        # Save user message for all modes (enables multi-turn history)
        db.execute(
            """INSERT INTO messages
               (id, project_id, session_id, role, content, output_mode, source_chunks,
                kredit_used, tokens_used_internal, created_at)
               VALUES (?, ?, ?, 'user', ?, ?, ?, 0, 0, ?)""",
            (
                str(uuid.uuid4()), project_id, active_session_id, body.query,
                body.output_mode, json.dumps([]), now,
            ),
        )
        msg_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO messages
               (id, project_id, session_id, role, content, output_mode, source_chunks,
                kredit_used, tokens_used_internal, created_at)
               VALUES (?, ?, ?, 'assistant', ?, ?, ?, ?, ?, ?)""",
            (
                msg_id, project_id, active_session_id, result["content"], body.output_mode,
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
        # Update session timestamp
        db.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE id = ?",
            (now, active_session_id)
        )
        # Clear summary cache if conversation has grown past trigger
        total_msgs = db.execute(
            "SELECT COUNT(*) as cnt FROM messages WHERE session_id = ?",
            (active_session_id,)
        ).fetchone()["cnt"]
        if total_msgs > SUMMARY_TRIGGER:
            db.execute(
                "UPDATE chat_sessions SET conversation_summary = '' WHERE id = ?",
                (active_session_id,)
            )
        # Auto-title on first user message (fire-and-forget)
        if total_msgs == 1:
            import asyncio
            asyncio.create_task(_auto_title_session(active_session_id, body.query))

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
def get_messages(project_id: str, session_id: str | None = None, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"]),
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")

        if session_id:
            msgs = db.execute(
                "SELECT * FROM messages WHERE project_id = ? AND session_id = ? ORDER BY created_at ASC",
                (project_id, session_id),
            ).fetchall()
        else:
            latest = db.execute("""
                SELECT id FROM chat_sessions
                WHERE project_id = ?
                ORDER BY updated_at DESC LIMIT 1
            """, (project_id,)).fetchone()
            if latest:
                msgs = db.execute(
                    "SELECT * FROM messages WHERE project_id = ? AND session_id = ? ORDER BY created_at ASC",
                    (project_id, latest["id"]),
                ).fetchall()
            else:
                msgs = []

    return [dict(m) for m in msgs]
