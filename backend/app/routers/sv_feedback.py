import json
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.llm_provider import call_deepseek_raw
from bs4 import BeautifulSoup

router = APIRouter()

VALID_STATUSES = {"open", "addressed", "dismissed"}

ALIGNMENT_PROMPT = """You are a research assistant reviewing a thesis chapter against supervisor feedback.

Supervisor feedback items (things the supervisor wants addressed):
{feedback_list}

Chapter content:
{content}

For each feedback item, determine if the chapter content adequately addresses it.
If NOT adequately addressed, flag it.

Return ONLY a valid JSON array. Each element:
{{"feedback_item": "exact feedback text", "concern": "brief explanation of gap", "suggestion": "concrete suggestion to address it"}}

If all feedback items are adequately addressed, return: []
No preamble, no markdown."""


def _verify_project(project_id: str, user_id: str, db):
    row = db.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id)
    ).fetchone()
    if not row:
        raise HTTPException(403, "Project not found or access denied.")
    return row


@router.get("/projects/{project_id}/sv-feedback")
def get_sv_feedback(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        _verify_project(project_id, user["user_id"], db)
        rows = db.execute(
            """SELECT id, feedback_text, status, doc_id, chapter_id, created_at, resolved_at
               FROM supervisor_feedback
               WHERE project_id = ?
               ORDER BY created_at DESC""",
            (project_id,)
        ).fetchall()
    return [dict(r) for r in rows]


class StatusUpdate(BaseModel):
    status: str
    chapter_id: Optional[str] = None


@router.patch("/projects/{project_id}/sv-feedback/{item_id}")
def update_sv_feedback_status(
    project_id: str, item_id: str, body: StatusUpdate,
    user=Depends(get_current_user)
):
    if body.status not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")

    with get_db() as db:
        _verify_project(project_id, user["user_id"], db)
        row = db.execute(
            "SELECT id FROM supervisor_feedback WHERE id = ? AND project_id = ?",
            (item_id, project_id)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Feedback item not found.")

        resolved_at = datetime.utcnow().isoformat() if body.status in ("addressed", "dismissed") else None
        db.execute(
            """UPDATE supervisor_feedback
               SET status = ?, resolved_at = ?, chapter_id = ?
               WHERE id = ? AND project_id = ?""",
            (body.status, resolved_at, body.chapter_id, item_id, project_id)
        )
    return {"id": item_id, "status": body.status}


class AlignmentRequest(BaseModel):
    content: str  # TipTap HTML content


@router.post("/projects/{project_id}/chapters/{chapter_id}/check-alignment")
async def check_alignment(
    project_id: str, chapter_id: str,
    body: AlignmentRequest,
    user=Depends(get_current_user)
):
    with get_db() as db:
        _verify_project(project_id, user["user_id"], db)
        chap = db.execute(
            "SELECT id FROM chapters WHERE id = ? AND project_id = ?",
            (chapter_id, project_id)
        ).fetchone()
        if not chap:
            raise HTTPException(404, "Chapter not found.")

        open_items = db.execute(
            """SELECT id, feedback_text FROM supervisor_feedback
               WHERE project_id = ? AND status = 'open'
               ORDER BY created_at ASC""",
            (project_id,)
        ).fetchall()

    if not open_items:
        return {"issues": [], "message": "No open SV feedback items to check against."}

    soup = BeautifulSoup(body.content, "html.parser")
    plain_content = soup.get_text(separator="\n", strip=True)

    if len(plain_content.strip()) < 50:
        return {"issues": [], "message": "Chapter content too short to analyse."}

    words = plain_content.split()
    if len(words) > 3000:
        plain_content = " ".join(words[:3000]) + "\n[content truncated]"

    feedback_list = "\n".join(
        f"{i+1}. {row['feedback_text']}" for i, row in enumerate(open_items)
    )

    prompt = ALIGNMENT_PROMPT.format(
        feedback_list=feedback_list,
        content=plain_content
    )

    try:
        raw = await call_deepseek_raw(prompt, max_tokens=1000)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        issues = json.loads(raw)
        if not isinstance(issues, list):
            issues = []
    except Exception:
        issues = []

    return {"issues": issues}
