import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.llm_provider import query_llm

router = APIRouter()


class ChapterCreate(BaseModel):
    title: str
    chapter_order: int


class ChapterContentUpdate(BaseModel):
    content: str


@router.post("/projects/{project_id}/chapters", status_code=201)
def create_chapter(project_id: str, body: ChapterCreate, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id=? AND user_id=?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")

        chap_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db.execute(
            "INSERT INTO chapters (id,project_id,title,chapter_order,status,created_at) VALUES (?,?,?,?,'draft',?)",
            (chap_id, project_id, body.title, body.chapter_order, now)
        )
        db.execute(
            "INSERT INTO chapter_content (id,chapter_id,content,summary,source_citations,updated_at) VALUES (?,?,'','','[]',?)",
            (str(uuid.uuid4()), chap_id, now)
        )
    return {"id": chap_id, "title": body.title, "chapter_order": body.chapter_order, "status": "draft"}


@router.get("/projects/{project_id}/chapters")
def list_chapters(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id=? AND user_id=?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")
        rows = db.execute(
            "SELECT * FROM chapters WHERE project_id=? ORDER BY chapter_order",
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


@router.patch("/projects/{project_id}/chapters/{chapter_id}/content")
async def update_chapter_content(
    project_id: str, chapter_id: str,
    body: ChapterContentUpdate,
    user=Depends(get_current_user)
):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id=? AND user_id=?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")

        chap = db.execute(
            "SELECT id FROM chapters WHERE id=? AND project_id=?",
            (chapter_id, project_id)
        ).fetchone()
        if not chap:
            raise HTTPException(404, "Bab tidak dijumpai.")

    # Generate summary for hierarchical context
    messages = [{
        "role": "user",
        "content": (
            f"Ringkaskan kandungan bab berikut dalam 150-200 patah perkataan sahaja, "
            f"fokus pada argumen utama dan dapatan:\n\n{body.content[:3000]}"
        )
    }]
    summary_result = await query_llm(messages, output_mode="qa")

    now = datetime.utcnow().isoformat()
    with get_db() as db:
        db.execute(
            "UPDATE chapter_content SET content=?, summary=?, updated_at=? WHERE chapter_id=?",
            (body.content, summary_result["content"], now, chapter_id)
        )
        db.execute(
            "UPDATE chapters SET status='dalam_proses' WHERE id=?",
            (chapter_id,)
        )
    return {"status": "updated", "summary_generated": True}
