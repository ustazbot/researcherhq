import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt


def make_headers(user_id="user-1", email="u1@test.com"):
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            yield c


def create_proj(client, user_id="user-1"):
    r = client.post("/projects", json={"title": "SV Project", "research_mode": "general"},
                    headers=make_headers(user_id))
    assert r.status_code == 201
    return r.json()["id"]


def seed_feedback(client, project_id, text="Revise Chapter 2 citations"):
    """Seed one feedback item directly via PATCH after inserting via DB."""
    # Insert via internal helper — use the API endpoint approach instead:
    # We seed by calling a private helper that inserts directly into DB.
    # Since there's no POST endpoint, we insert via the DB fixture.
    # Use the client's app state to get the DB path.
    import sqlite3
    import uuid
    from datetime import datetime
    # Access the patched db path from the app
    from app import database
    item_id = str(uuid.uuid4())
    with database.get_db() as db:
        db.execute(
            """INSERT INTO supervisor_feedback (id, project_id, doc_id, feedback_text, status, created_at)
               VALUES (?, ?, NULL, ?, 'open', ?)""",
            (item_id, project_id, text, datetime.utcnow().isoformat())
        )
    return item_id


def create_chapter(client, project_id, user_id="user-1"):
    r = client.post(f"/projects/{project_id}/chapters",
                    json={"title": "Chapter 1", "chapter_order": 1},
                    headers=make_headers(user_id))
    assert r.status_code == 201
    return r.json()["id"]


# ── Schema ────────────────────────────────────────────────────────────────────

def test_supervisor_feedback_table_exists(client):
    from app import database
    with database.get_db() as db:
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='supervisor_feedback'"
        ).fetchall()
    assert len(rows) == 1


# ── GET /projects/{id}/sv-feedback ────────────────────────────────────────────

def test_get_sv_feedback_empty_returns_list(client):
    pid = create_proj(client)
    r = client.get(f"/projects/{pid}/sv-feedback", headers=make_headers())
    assert r.status_code == 200
    assert r.json() == []


def test_get_sv_feedback_wrong_project_denied(client):
    pid = create_proj(client, user_id="user-1")
    r = client.get(f"/projects/{pid}/sv-feedback",
                   headers=make_headers("user-2", "u2@test.com"))
    assert r.status_code == 403


# ── PATCH /projects/{id}/sv-feedback/{item_id} ───────────────────────────────

def test_patch_sv_feedback_status_addressed(client):
    pid = create_proj(client)
    item_id = seed_feedback(client, pid)
    r = client.patch(f"/projects/{pid}/sv-feedback/{item_id}",
                     json={"status": "addressed"},
                     headers=make_headers())
    assert r.status_code == 200
    assert r.json()["status"] == "addressed"

    # Verify persisted
    r2 = client.get(f"/projects/{pid}/sv-feedback", headers=make_headers())
    item = next(i for i in r2.json() if i["id"] == item_id)
    assert item["status"] == "addressed"
    assert item["resolved_at"] is not None


def test_patch_sv_feedback_status_dismissed(client):
    pid = create_proj(client)
    item_id = seed_feedback(client, pid, "Add more references")
    r = client.patch(f"/projects/{pid}/sv-feedback/{item_id}",
                     json={"status": "dismissed"},
                     headers=make_headers())
    assert r.status_code == 200
    assert r.json()["status"] == "dismissed"


def test_patch_sv_feedback_invalid_status_rejected(client):
    pid = create_proj(client)
    item_id = seed_feedback(client, pid)
    r = client.patch(f"/projects/{pid}/sv-feedback/{item_id}",
                     json={"status": "invalid_status"},
                     headers=make_headers())
    assert r.status_code == 400


def test_patch_sv_feedback_wrong_project_denied(client):
    pid = create_proj(client, user_id="user-1")
    item_id = seed_feedback(client, pid)
    r = client.patch(f"/projects/{pid}/sv-feedback/{item_id}",
                     json={"status": "addressed"},
                     headers=make_headers("user-2", "u2@test.com"))
    assert r.status_code == 403


# ── POST check-alignment ──────────────────────────────────────────────────────

def test_check_alignment_no_open_items(client):
    pid = create_proj(client)
    chap_id = create_chapter(client, pid)
    r = client.post(
        f"/projects/{pid}/chapters/{chap_id}/check-alignment",
        json={"content": "<p>Some chapter content here that is long enough.</p>"},
        headers=make_headers()
    )
    assert r.status_code == 200
    data = r.json()
    assert data["issues"] == []
    assert "No open" in data.get("message", "")


def test_check_alignment_with_content(client):
    pid = create_proj(client)
    chap_id = create_chapter(client, pid)
    seed_feedback(client, pid, "Add sample size justification")

    mock_response = '[{"feedback_item": "Add sample size justification", "concern": "Not mentioned", "suggestion": "Add a paragraph explaining sample size rationale"}]'

    with patch("app.routers.sv_feedback.call_deepseek_raw", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = mock_response
        r = client.post(
            f"/projects/{pid}/chapters/{chap_id}/check-alignment",
            json={"content": "<p>" + "This is chapter content. " * 20 + "</p>"},
            headers=make_headers()
        )

    assert r.status_code == 200
    issues = r.json()["issues"]
    assert len(issues) == 1
    assert issues[0]["feedback_item"] == "Add sample size justification"
    assert "concern" in issues[0]
    assert "suggestion" in issues[0]


# ── Cascade delete ────────────────────────────────────────────────────────────

def test_sv_feedback_cascade_delete_project(client):
    pid = create_proj(client)
    seed_feedback(client, pid, "Fix citation format")

    # Verify item exists
    r = client.get(f"/projects/{pid}/sv-feedback", headers=make_headers())
    assert len(r.json()) == 1

    # Delete project
    r2 = client.delete(f"/projects/{pid}", headers=make_headers())
    assert r2.status_code == 204

    # Verify feedback gone from DB
    from app import database
    with database.get_db() as db:
        rows = db.execute(
            "SELECT id FROM supervisor_feedback WHERE project_id = ?", (pid,)
        ).fetchall()
    assert len(rows) == 0
