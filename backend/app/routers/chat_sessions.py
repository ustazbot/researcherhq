import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()


@router.get("/{project_id}/sessions")
def list_sessions(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")

        sessions = db.execute("""
            SELECT cs.id, cs.title, cs.created_at, cs.updated_at,
                   COUNT(m.id) as message_count
            FROM chat_sessions cs
            LEFT JOIN messages m ON m.session_id = cs.id
            WHERE cs.project_id = ?
            GROUP BY cs.id
            ORDER BY cs.updated_at DESC
        """, (project_id,)).fetchall()

    return [dict(s) for s in sessions]


@router.post("/{project_id}/sessions", status_code=201)
def create_session(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        proj = db.execute(
            "SELECT id FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        ).fetchone()
        if not proj:
            raise HTTPException(404, "Projek tidak dijumpai.")

        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db.execute("""
            INSERT INTO chat_sessions (id, project_id, title, created_at, updated_at)
            VALUES (?, ?, 'Chat Baru', ?, ?)
        """, (session_id, project_id, now, now))

    return {"id": session_id, "title": "Chat Baru", "created_at": now, "message_count": 0}


class SessionUpdate(BaseModel):
    title: str


@router.patch("/{project_id}/sessions/{session_id}")
def rename_session(
    project_id: str,
    session_id: str,
    body: SessionUpdate,
    user=Depends(get_current_user)
):
    if not body.title.strip():
        raise HTTPException(400, "Tajuk sesi tidak boleh kosong.")

    with get_db() as db:
        sess = db.execute("""
            SELECT cs.id FROM chat_sessions cs
            JOIN projects p ON p.id = cs.project_id
            WHERE cs.id = ? AND cs.project_id = ? AND p.user_id = ?
        """, (session_id, project_id, user["user_id"])).fetchone()
        if not sess:
            raise HTTPException(404, "Sesi tidak dijumpai.")

        now = datetime.utcnow().isoformat()
        db.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (body.title.strip(), now, session_id)
        )

    return {"id": session_id, "title": body.title.strip()}


@router.delete("/{project_id}/sessions/{session_id}", status_code=200)
def delete_session(
    project_id: str,
    session_id: str,
    user=Depends(get_current_user)
):
    with get_db() as db:
        sess = db.execute("""
            SELECT cs.id FROM chat_sessions cs
            JOIN projects p ON p.id = cs.project_id
            WHERE cs.id = ? AND cs.project_id = ? AND p.user_id = ?
        """, (session_id, project_id, user["user_id"])).fetchone()
        if not sess:
            raise HTTPException(404, "Sesi tidak dijumpai.")

        session_count = db.execute(
            "SELECT COUNT(*) as cnt FROM chat_sessions WHERE project_id = ?",
            (project_id,)
        ).fetchone()["cnt"]
        if session_count <= 1:
            raise HTTPException(400, "Tidak boleh padam sesi terakhir. Buat sesi baru dahulu.")

        db.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))

    return {"deleted": session_id}
