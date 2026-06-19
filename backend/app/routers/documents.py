import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.rag_pipeline import chunk_text

router = APIRouter()

VALID_CATEGORIES = {"artikel", "catatan_sv", "draf", "data"}

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

    # Queue embedding (will be implemented in Task 6)
    # For now, return immediately
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
