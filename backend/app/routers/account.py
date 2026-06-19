import sqlite3
import sqlite_vec
import app.database as _db_module
from fastapi import APIRouter, Depends, HTTPException, Response
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()


def _delete_user_account(user_id: str, db_path: str = None):
    path = db_path or _db_module._db_path
    conn = sqlite3.connect(path)
    sqlite_vec.load(conn)
    # FK OFF so we can set billing_events.user_id = 'deleted_user' (sentinel, not a real user)
    # All cascades handled manually below.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        # Step 1: Delete chunk_vectors — vec0 virtual table, no FK cascade
        chunk_ids = conn.execute(
            """SELECT c.id FROM chunks c
               JOIN documents d ON c.doc_id = d.id
               JOIN projects p ON d.project_id = p.id
               WHERE p.user_id = ?""",
            (user_id,)
        ).fetchall()
        for (chunk_id,) in chunk_ids:
            conn.execute("DELETE FROM chunk_vectors WHERE rowid = ?", (chunk_id,))

        # Step 2: Anonymise billing_events — PDPA audit trail kept, identity removed
        conn.execute(
            "UPDATE billing_events SET user_id = 'deleted_user' WHERE user_id = ?",
            (user_id,)
        )

        # Step 3: SET NULL for support_reports (mirrors ON DELETE SET NULL)
        conn.execute(
            "UPDATE support_reports SET user_id = NULL WHERE user_id = ?",
            (user_id,)
        )

        # Step 4: Manual cascade — deepest tables first
        conn.execute(
            """DELETE FROM chapter_content WHERE chapter_id IN (
               SELECT ch.id FROM chapters ch
               JOIN projects p ON ch.project_id = p.id
               WHERE p.user_id = ?)""",
            (user_id,)
        )
        conn.execute(
            "DELETE FROM chapters WHERE project_id IN (SELECT id FROM projects WHERE user_id = ?)",
            (user_id,)
        )
        conn.execute(
            """DELETE FROM chunks WHERE doc_id IN (
               SELECT d.id FROM documents d
               JOIN projects p ON d.project_id = p.id
               WHERE p.user_id = ?)""",
            (user_id,)
        )
        conn.execute(
            "DELETE FROM documents WHERE project_id IN (SELECT id FROM projects WHERE user_id = ?)",
            (user_id,)
        )
        conn.execute(
            "DELETE FROM messages WHERE project_id IN (SELECT id FROM projects WHERE user_id = ?)",
            (user_id,)
        )
        conn.execute(
            "DELETE FROM query_cache WHERE project_id IN (SELECT id FROM projects WHERE user_id = ?)",
            (user_id,)
        )
        conn.execute("DELETE FROM projects WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM user_interactions WHERE user_id = ?", (user_id,))

        # Step 5: Delete user
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@router.get("")
def get_account(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            "SELECT id, email, tier, kredit_remaining, kredit_total, reset_date, created_at FROM users WHERE id = ?",
            (user["user_id"],)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Pengguna tidak dijumpai.")

    return {
        "id": row["id"],
        "email": row["email"],
        "tier": row["tier"],
        "kredit_remaining": row["kredit_remaining"],
        "kredit_total": row["kredit_total"],
        "reset_date": row["reset_date"],
        "created_at": row["created_at"],
    }


@router.delete("", status_code=204)
def delete_account(user=Depends(get_current_user)):
    _delete_user_account(user["user_id"])
    return Response(status_code=204)
