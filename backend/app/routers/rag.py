import uuid
import json
import hashlib
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user
from app.services.embedding_pool import embedding_pool
from app.services.rag_pipeline import retrieve_chunks
from app.services.llm_provider import query_llm, KREDIT_COST

router = APIRouter()

OUTPUT_MODES = {"qa", "literature_review", "executive_summary", "key_findings", "research_gap"}

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
            "SELECT kredit_remaining, tier FROM users WHERE id = ?",
            (user["user_id"],),
        ).fetchone()

        mode_key = "qa_deep" if (body.query_type == "deep" and body.output_mode == "qa") else body.output_mode
        kredit_cost = KREDIT_COST.get(mode_key, 1)

        if user_row["kredit_remaining"] < kredit_cost:
            raise HTTPException(402, "Kredit Kajian tidak mencukupi.")

        project_dict = dict(proj)

    # Embed query
    query_embedding = await embedding_pool.embed(body.query)

    # Retrieve relevant chunks
    chunks = await retrieve_chunks(
        project_id=project_id,
        query_embedding=query_embedding,
        query_type=body.query_type,
        db_path=settings.database_url,
    )

    if not chunks:
        return {
            "answer": "Tiada dokumen dalam projek ini atau dokumen belum selesai diproses. Sila muat naik dokumen dan tunggu sebentar sebelum bertanya.",
            "sources": [],
            "kredit_used": 0,
            "kredit_remaining": user_row["kredit_remaining"],
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

    messages = [
        {
            "role": "user",
            "content": f"KONTEKS DOKUMEN:\n\n{context}\n\n---\n\nSOALAN: {body.query}",
        }
    ]

    result = await query_llm(
        messages=messages,
        research_mode=project_dict["research_mode"],
        output_mode=body.output_mode,
        query_type=body.query_type,
    )

    # Deduct kredit, save message, log interaction
    with get_db() as db:
        new_kredit = user_row["kredit_remaining"] - kredit_cost
        db.execute(
            """UPDATE users SET kredit_remaining = ?,
               tokens_used_internal = tokens_used_internal + ?
               WHERE id = ?""",
            (new_kredit, result["tokens_used"], user["user_id"]),
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
                kredit_cost, result["tokens_used"], datetime.utcnow().isoformat(),
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
