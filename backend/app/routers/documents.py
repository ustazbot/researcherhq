import asyncio
import sqlite3
import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
import app.database as _db_module
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.rag_pipeline import chunk_text
from app.services.ocr_service import is_scanned_pdf
from app.services.sv_extractor import extract_sv_feedback
import sqlite_vec as _sqlite_vec

router = APIRouter()

VALID_CATEGORIES = {"artikel", "catatan_sv", "draf", "data", "proposal", "panduan_format"}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}

async def _extract_and_store_sv_feedback(doc_id: str, project_id: str, full_text: str):
    """Background task: extract SV feedback items and store in DB."""
    import uuid
    from datetime import datetime
    items = await extract_sv_feedback(full_text)
    if not items:
        return
    now = datetime.utcnow().isoformat()
    with get_db() as db:
        for item_text in items:
            db.execute(
                """INSERT INTO supervisor_feedback (id, project_id, doc_id, feedback_text, status, created_at)
                   VALUES (?, ?, ?, ?, 'open', ?)""",
                (str(uuid.uuid4()), project_id, doc_id, item_text, now)
            )


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
                (chunk_id, _sqlite_vec.serialize_float32(embedding))
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

    # Auto-extract SV feedback if category is catatan_sv
    if body.category == "catatan_sv":
        full_text = "\n\n".join(
            p.text for p in body.pages if p.text and p.text.strip()
        )
        if full_text.strip():
            asyncio.create_task(
                _extract_and_store_sv_feedback(doc_id, body.project_id, full_text)
            )

    return {
        "id": doc_id,
        "filename": body.filename,
        "chunk_count": len(all_chunks),
        "status": "uploaded",
        "message": "Dokumen berjaya dimuat naik. Embedding sedang diproses..."
    }

@router.post("/upload-office", status_code=201)
async def upload_office_document(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    category: str = Form("data"),
    user=Depends(get_current_user),
):
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, "Only DOCX, XLSX, and PPTX files are supported.")

    file_type = ALLOWED_MIME_TYPES[file.content_type]

    file_bytes = await file.read()

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large. Maximum size is 20MB.")

    if category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Invalid category: {category}")

    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"]),
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Project not found.")

        user_row = db.execute(
            "SELECT tier FROM users WHERE id = ?", (user["user_id"],)
        ).fetchone()
        tier = user_row["tier"] if user_row else "free"

        doc_count = db.execute(
            "SELECT COUNT(*) as c FROM documents WHERE project_id = ?",
            (project_id,),
        ).fetchone()["c"]

        max_docs = 1 if tier == "free" else 5
        if doc_count >= max_docs:
            raise HTTPException(403, f"Document limit ({max_docs}) reached.")

    from app.services.office_parser import extract_docx, extract_xlsx, extract_pptx
    try:
        if file_type == "docx":
            pages = extract_docx(file_bytes)
        elif file_type == "xlsx":
            pages = extract_xlsx(file_bytes)
        else:
            pages = extract_pptx(file_bytes)
    except Exception:
        raise HTTPException(
            422,
            f"Failed to parse {file_type.upper()} file. File may be corrupted or password-protected.",
        )

    del file_bytes

    if not pages:
        raise HTTPException(422, "No text content found in the file.")

    with get_db() as db:
        doc_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        all_chunks = []
        for page in pages:
            if page["text"] and page["text"].strip():
                page_chunks = chunk_text(page["text"], page_number=page["page_number"])
                all_chunks.extend(page_chunks)

        db.execute(
            """INSERT INTO documents (id, project_id, filename, category, page_count, chunk_count, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, project_id, file.filename, category, len(pages), len(all_chunks), now),
        )

        for chunk in all_chunks:
            chunk_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO chunks (id, doc_id, page_number, chunk_index, text, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (chunk_id, doc_id, chunk["page_number"], chunk["chunk_index"], chunk["text"], now),
            )

        db.execute(
            "UPDATE projects SET document_set_version = document_set_version + 1 WHERE id = ?",
            (project_id,),
        )

        saved_chunk_ids = [
            row["id"]
            for row in db.execute(
                "SELECT id FROM chunks WHERE doc_id = ? ORDER BY chunk_index", (doc_id,)
            ).fetchall()
        ]
        chunk_texts_for_embedding = [c["text"] for c in all_chunks]

    if chunk_texts_for_embedding:
        asyncio.create_task(
            _embed_and_store_chunks(doc_id, chunk_texts_for_embedding, saved_chunk_ids)
        )

    # Auto-extract SV feedback if category is catatan_sv
    if category == "catatan_sv":
        full_text = "\n\n".join(
            p["text"] for p in pages if p.get("text", "").strip()
        )
        if full_text.strip():
            asyncio.create_task(
                _extract_and_store_sv_feedback(doc_id, project_id, full_text)
            )

    return {
        "id": doc_id,
        "filename": file.filename,
        "file_type": file_type,
        "chunk_count": len(all_chunks),
        "page_count": len(pages),
        "status": "uploaded",
        "message": f"{file_type.upper()} processed successfully. Embedding in progress...",
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


@router.get("/{doc_id}/preview")
def get_document_preview(doc_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        doc = db.execute(
            """SELECT d.id, d.filename, d.chunk_count FROM documents d
               JOIN projects p ON d.project_id = p.id
               WHERE d.id = ? AND p.user_id = ?""",
            (doc_id, user["user_id"])
        ).fetchone()
        if not doc:
            raise HTTPException(404, "Dokumen tidak dijumpai.")
        chunks = db.execute(
            "SELECT text FROM chunks WHERE doc_id = ? ORDER BY page_number, chunk_index LIMIT 20",
            (doc_id,)
        ).fetchall()
    preview_text = "\n\n---\n\n".join(row["text"] for row in chunks)
    return {
        "doc_id": doc_id,
        "filename": doc["filename"],
        "preview_text": preview_text,
        "chunk_count": doc["chunk_count"],
        "showing_chunks": len(chunks),
    }


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
