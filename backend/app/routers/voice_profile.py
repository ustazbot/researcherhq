import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()


def _verify_project(project_id: str, user_id: str, db):
    row = db.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(403, "Projek tidak dijumpai atau akses ditolak.")
    return row


def build_style_notes(answers: dict, sample_excerpt: str = None, sample_analysis: str = None) -> str:
    lines = ["GAYA PENULISAN USER (ikut keutamaan ini):"]
    q_labels = {
        "q1": "Panjang ayat",
        "q2": "Gaya penulisan",
        "q3": "Keutamaan lain",
    }
    for key, label in q_labels.items():
        if answers.get(key):
            lines.append(f"- {label}: {answers[key]}")
    if sample_analysis:
        lines.append(f"- Analisis gaya tulisan (daripada sampel): {sample_analysis[:400]}")
    elif sample_excerpt:
        excerpt = sample_excerpt[:300].strip()
        lines.append(f'- Contoh gaya tulisan user: "{excerpt}"')
    return "\n".join(lines)


@router.get("/{project_id}")
def get_voice_profile(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        _verify_project(project_id, user["user_id"], db)
        row = db.execute(
            "SELECT style_notes, sample_excerpt, sample_analysis, updated_at FROM voice_profile WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "style_notes": row["style_notes"],
        "sample_excerpt": row["sample_excerpt"],
        "sample_analysis": row["sample_analysis"],
        "updated_at": row["updated_at"],
    }


class VoiceProfileBody(BaseModel):
    answers: dict
    sample_excerpt: Optional[str] = None
    sample_analysis: Optional[str] = None


@router.post("/{project_id}")
def save_voice_profile(
    project_id: str,
    body: VoiceProfileBody,
    user=Depends(get_current_user),
):
    with get_db() as db:
        _verify_project(project_id, user["user_id"], db)

        user_row = db.execute(
            "SELECT tier FROM users WHERE id = ?", (user["user_id"],)
        ).fetchone()
        if not user_row or user_row["tier"] != "pro":
            raise HTTPException(403, "Profil Gaya Penulisan hanya tersedia untuk pengguna Pro.")

        excerpt = body.sample_excerpt[:500].strip() if body.sample_excerpt else None
        analysis = body.sample_analysis[:2000].strip() if body.sample_analysis else None
        style_notes = build_style_notes(body.answers, excerpt, analysis)
        now = datetime.utcnow().isoformat()

        existing = db.execute(
            "SELECT id FROM voice_profile WHERE project_id = ?", (project_id,)
        ).fetchone()

        if existing:
            db.execute(
                """UPDATE voice_profile
                   SET style_notes = ?, sample_excerpt = ?, sample_analysis = ?, updated_at = ?
                   WHERE project_id = ?""",
                (style_notes, excerpt, analysis, now, project_id),
            )
            row_id = existing["id"]
        else:
            row_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO voice_profile
                   (id, project_id, style_notes, sample_excerpt, sample_analysis, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (row_id, project_id, style_notes, excerpt, analysis, now, now),
            )

    return {
        "exists": True,
        "style_notes": style_notes,
        "sample_excerpt": excerpt,
        "sample_analysis": analysis,
        "updated_at": now,
    }
