import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uuid
import sqlite3
import pytest
from datetime import datetime
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_user(conn, email, tier="free", kredit=50):
    uid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO users (id, email, tier, kredit_remaining, kredit_total,
           kredit_subscription, kredit_topup, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
        (uid, email, tier, kredit, kredit, kredit, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return uid


def _make_project(conn, user_id):
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO projects (id, user_id, title, research_mode, created_at) VALUES (?, ?, 'Test', 'general', ?)",
        (pid, user_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    return pid


def _make_session(conn, project_id, title="Chat Baru"):
    sid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO chat_sessions (id, project_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (sid, project_id, title, now, now),
    )
    conn.commit()
    return sid


@pytest.fixture
def setup(tmp_path):
    db_path = str(tmp_path / "sessions_test.db")
    from app.database import init_db
    with patch("app.database._db_path", db_path):
        init_db(db_path)
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        user_id = _make_user(conn, "user@test.com")
        other_id = _make_user(conn, "other@test.com")
        proj_id = _make_project(conn, user_id)
        conn.close()

        from app.services.auth_service import create_jwt
        token = create_jwt({"user_id": user_id, "email": "user@test.com"})
        other_token = create_jwt({"user_id": other_id, "email": "other@test.com"})

        from app.main import app
        with TestClient(app) as c:
            yield {
                "client": c,
                "db_path": db_path,
                "user_id": user_id,
                "proj_id": proj_id,
                "headers": {"Authorization": f"Bearer {token}"},
                "other_headers": {"Authorization": f"Bearer {other_token}"},
            }


# ── 31A: Schema ───────────────────────────────────────────────────────────────

def test_chat_sessions_table_exists(setup):
    conn = sqlite3.connect(setup["db_path"])
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    assert "chat_sessions" in tables


def test_messages_has_session_id_column(setup):
    conn = sqlite3.connect(setup["db_path"])
    cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
    conn.close()
    assert "session_id" in cols


# ── 31B: CRUD ─────────────────────────────────────────────────────────────────

def test_list_sessions_empty(setup):
    r = setup["client"].get(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_create_session(setup):
    r = setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Chat Baru"
    assert "id" in data


def test_list_sessions_returns_created(setup):
    setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    r = setup["client"].get(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    assert len(r.json()) == 2


def test_rename_session(setup):
    create = setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    sid = create.json()["id"]
    r = setup["client"].patch(
        f"/projects/{setup['proj_id']}/sessions/{sid}",
        json={"title": "Kajian Baru"},
        headers=setup["headers"],
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Kajian Baru"


def test_rename_session_empty_title_rejected(setup):
    create = setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    sid = create.json()["id"]
    r = setup["client"].patch(
        f"/projects/{setup['proj_id']}/sessions/{sid}",
        json={"title": "   "},
        headers=setup["headers"],
    )
    assert r.status_code == 400


def test_delete_last_session_blocked(setup):
    create = setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    sid = create.json()["id"]
    r = setup["client"].delete(
        f"/projects/{setup['proj_id']}/sessions/{sid}",
        headers=setup["headers"],
    )
    assert r.status_code == 400


def test_delete_session_allowed_when_multiple(setup):
    s1 = setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"]).json()["id"]
    s2 = setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"]).json()["id"]
    r = setup["client"].delete(f"/projects/{setup['proj_id']}/sessions/{s1}", headers=setup["headers"])
    assert r.status_code == 200
    remaining = setup["client"].get(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"]).json()
    assert len(remaining) == 1
    assert remaining[0]["id"] == s2


def test_cannot_access_other_users_sessions(setup):
    r = setup["client"].get(f"/projects/{setup['proj_id']}/sessions", headers=setup["other_headers"])
    assert r.status_code == 404


def test_cannot_delete_other_users_session(setup):
    sid = setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"]).json()["id"]
    setup["client"].post(f"/projects/{setup['proj_id']}/sessions", headers=setup["headers"])
    r = setup["client"].delete(
        f"/projects/{setup['proj_id']}/sessions/{sid}",
        headers=setup["other_headers"],
    )
    assert r.status_code == 404


# ── 31C: GET /messages filtered by session_id ─────────────────────────────────

def test_get_messages_returns_latest_session_by_default(setup):
    conn = sqlite3.connect(setup["db_path"])
    conn.row_factory = sqlite3.Row
    sid = _make_session(conn, setup["proj_id"], "Sesi A")
    msg_id = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO messages (id, project_id, session_id, role, content, output_mode,
           source_chunks, kredit_used, tokens_used_internal, created_at)
           VALUES (?, ?, ?, 'assistant', 'hello', 'qa', '[]', 1, 0, ?)""",
        (msg_id, setup["proj_id"], sid, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    r = setup["client"].get(f"/projects/{setup['proj_id']}/messages", headers=setup["headers"])
    assert r.status_code == 200
    assert any(m["session_id"] == sid for m in r.json())


def test_get_messages_filtered_by_session_id(setup):
    conn = sqlite3.connect(setup["db_path"])
    conn.row_factory = sqlite3.Row
    sid_a = _make_session(conn, setup["proj_id"], "Sesi A")
    sid_b = _make_session(conn, setup["proj_id"], "Sesi B")
    for sid, content in [(sid_a, "msg a"), (sid_b, "msg b")]:
        conn.execute(
            """INSERT INTO messages (id, project_id, session_id, role, content, output_mode,
               source_chunks, kredit_used, tokens_used_internal, created_at)
               VALUES (?, ?, ?, 'assistant', ?, 'qa', '[]', 1, 0, ?)""",
            (str(uuid.uuid4()), setup["proj_id"], sid, content, datetime.utcnow().isoformat()),
        )
    conn.commit()
    conn.close()

    r = setup["client"].get(f"/projects/{setup['proj_id']}/messages?session_id={sid_a}", headers=setup["headers"])
    assert r.status_code == 200
    msgs = r.json()
    assert all(m["session_id"] == sid_a for m in msgs)
    assert any(m["content"] == "msg a" for m in msgs)
    assert not any(m["content"] == "msg b" for m in msgs)
