import asyncio
import sqlite3
import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
import app.database as _db_module
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.rag_pipeline import chunk_text
from app.services.ocr_service import is_scanned_pdf
import sqlite_vec as _sqlite_vec

router = APIRouter()

VALID_CATEGORIES = {"artikel", "catatan_sv", "draf", "data", "proposal"}

async def _embed_and_store_chunks(doc_id: str, chunk_texts: List[str], chunk_ids: List[str]):
    """Background task: embed chunks and store in chunk_vectors."""
    from app.services.embedding_pool import embedding_pool
    try:
        embeddings = await embedding_pool.embed_batch(chunk_texts)
        conn = sqlite3.connect(_db_module._db_path)
        _sqlite_vec.load(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            conn.execute(
                "INSERT INTO chunk_vectors (chunk_id, embedding) VALUES (?, ?)",
                (chunk_id, embedding)
            )
        conn.commit()
        conn.close()
    except Exception as e:
        # Log but don't crash — embedding is best-effort in background
        print(f"Embedding error for doc {doc_id}: {e}")

class PageData(BaseModel):
    page_number: int
    text: str

class DocumentUpload(BaseModel):
    project_id: str
    filename: str
    category: str = "artikel"
    pages: List[PageData]

@router.post("/upload", status_code=201)
async def upload_document(body: DocumentUpload, user=Depends(get_current_user)):
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Kategori tidak sah: {body.category}")

    # Scanned PDF check — based on avg token count per page
    pages_as_dicts = [{"text": p.text} for p in body.pages]
    if is_scanned_pdf(pages_as_dicts):
        with get_db() as db:
            user_row = db.execute("SELECT tier FROM users WHERE id = ?", (user["user_id"],)).fetchone()
            tier_check = user_row["tier"] if user_row else "free"
        if tier_check != "pro":
            raise HTTPException(
                403,
                "PDF ini nampak seperti dokumen imbasan. Naik taraf ke Pro untuk proses PDF imbasan."
            )

    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (body.project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")

        user_row = db.execute(
            "SELECT tier FROM users WHERE id = ?", (user["user_id"],)
        ).fetchone()
        tier = user_row["tier"] if user_row else "free"

        doc_count = db.execute(
            "SELECT COUNT(*) as c FROM documents WHERE project_id = ?",
            (body.project_id,)
        ).fetchone()["c"]

        max_docs = 1 if tier == "free" else 5
        if doc_count >= max_docs:
            raise HTTPException(403, f"Had dokumen ({max_docs} serentak) tercapai.")

        doc_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        all_chunks = []
        for page in body.pages:
            if page.text and page.text.strip():
                page_chunks = chunk_text(page.text, page_number=page.page_number)
                all_chunks.extend(page_chunks)

        db.execute(
            """INSERT INTO documents (id, project_id, filename, category, page_count, chunk_count, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, body.project_id, body.filename, body.category,
             len(body.pages), len(all_chunks), now)
        )

        for chunk in all_chunks:
            chunk_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO chunks (id, doc_id, page_number, chunk_index, text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chunk_id, doc_id, chunk["page_number"], chunk["chunk_index"], chunk["text"], now)
            )

        # Bump document_set_version for cache invalidation
        db.execute(
            "UPDATE projects SET document_set_version = document_set_version + 1 WHERE id = ?",
            (body.project_id,)
        )

        # Collect chunk IDs for background embedding
        saved_chunk_ids = [
            row["id"] for row in db.execute(
                "SELECT id FROM chunks WHERE doc_id = ? ORDER BY chunk_index",
                (doc_id,)
            ).fetchall()
        ]
        chunk_texts_for_embedding = [c["text"] for c in all_chunks]

    # Schedule background embedding (outside get_db context)
    if chunk_texts_for_embedding:
        asyncio.create_task(
            _embed_and_store_chunks(doc_id, chunk_texts_for_embedding, saved_chunk_ids)
        )

    return {
        "id": doc_id,
        "filename": body.filename,
        "chunk_count": len(all_chunks),
        "status": "uploaded",
        "message": "Dokumen berjaya dimuat naik. Embedding sedang diproses..."
    }

@router.get("")
def list_documents(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        docs = db.execute(
            "SELECT * FROM documents WHERE project_id = ? ORDER BY uploaded_at DESC",
            (project_id,)
        ).fetchall()
    return [dict(d) for d in docs]

@router.get("/{doc_id}")
def get_document(doc_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        doc = db.execute(
            """SELECT d.* FROM documents d
               JOIN projects p ON d.project_id = p.id
               WHERE d.id = ? AND p.user_id = ?""",
            (doc_id, user["user_id"])
        ).fetchone()
    if not doc:
        raise HTTPException(404, "Dokumen tidak dijumpai.")
    return dict(doc)


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        doc = db.execute(
            """SELECT d.id, d.project_id FROM documents d
               JOIN projects p ON d.project_id = p.id
               WHERE d.id=? AND p.user_id=?""",
            (doc_id, user["user_id"])
        ).fetchone()
        if not doc:
            raise HTTPException(404, "Dokumen tidak dijumpai.")
        project_id = doc["project_id"]

        # chunk_vectors adalah virtual table — tiada FK cascade, perlu padam manual
        chunk_ids = [
            row["id"] for row in db.execute(
                "SELECT id FROM chunks WHERE doc_id=?", (doc_id,)
            ).fetchall()
        ]
        for chunk_id in chunk_ids:
            db.execute("DELETE FROM chunk_vectors WHERE chunk_id=?", (chunk_id,))

        # padam dokumen — chunks cascade via FK ON DELETE CASCADE
        db.execute("DELETE FROM documents WHERE id=?", (doc_id,))

        # invalidate query cache
        db.execute(
            "UPDATE projects SET document_set_version = document_set_version + 1 WHERE id=?",
            (project_id,)
        )
