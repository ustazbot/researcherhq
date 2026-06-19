import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch
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

@pytest.fixture
def client_with_user(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            # Trigger user creation by creating a project
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)
            yield c, headers, "user-1"

def test_get_credits(client_with_user):
    client, headers, user_id = client_with_user
    r = client.get("/credits", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["kredit_remaining"] == 50
    assert data["kredit_total"] == 50
    assert data["tier"] == "free"
    assert "reset_date" in data

def test_get_account(client_with_user):
    client, headers, user_id = client_with_user
    r = client.get("/account", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "u1@test.com"
    assert data["tier"] == "free"

def test_delete_account_cascades(client_with_user, tmp_path):
    """Padam account → semua data cascade delete."""
    import sqlite3, sqlite_vec as sv
    client, headers, user_id = client_with_user
    db_path = str(tmp_path / "test.db")

    # Upload a project to have data
    proj_r = client.post("/projects", json={"title": "T2", "research_mode": "general"},
                         headers=make_headers("user-2", "u2@test.com"))
    # Delete user-1's account
    r = client.delete("/account", headers=headers)
    assert r.status_code == 204

    # Verify data is gone
    with patch("app.database._db_path", db_path):
        from app.database import get_db
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            assert user is None

def test_billing_events_anonymized_not_deleted(tmp_path):
    """billing_events kekal tapi user_id jadi 'deleted_user' selepas padam akaun."""
    import sqlite3
    import sqlite_vec as sv
    import uuid
    from datetime import datetime

    db_path = str(tmp_path / "billing_test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db, get_db
        init_db(db_path)

        user_id = str(uuid.uuid4())
        # Insert user + billing event directly
        conn = sqlite3.connect(db_path)
        sv.load(conn)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO users (id, email, tier, kredit_remaining, kredit_total, tokens_used_internal, created_at) VALUES (?, ?, 'free', 50, 50, 0, ?)",
            (user_id, "billing@test.com", datetime.utcnow().isoformat())
        )
        billing_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, created_at) VALUES (?, ?, 'topup', 10.0, 200, ?)",
            (billing_id, user_id, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()

        # Now delete account via the service function
        from app.routers.account import _delete_user_account
        _delete_user_account(user_id, db_path)

        # Verify: billing_event exists but user_id is 'deleted_user'
        conn = sqlite3.connect(db_path)
        sv.load(conn)
        row = conn.execute("SELECT user_id FROM billing_events WHERE id = ?", (billing_id,)).fetchone()
        conn.close()
        assert row is not None, "billing_event harus kekal"
        assert row[0] == "deleted_user", f"Expected 'deleted_user' but got: {row[0]}"
