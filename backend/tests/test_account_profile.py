import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import init_db, get_db
from app.services.auth_service import create_jwt
import uuid

def make_token(user_id=None, email=None):
    uid = user_id or str(uuid.uuid4())
    em = email or f"test_{uuid.uuid4().hex[:6]}@test.com"
    return create_jwt({"user_id": uid, "email": em}), uid, em

@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            yield c, db_path

def _seed_user(db_path, user_id, email):
    """Insert a user row directly so GET /account can find it."""
    from datetime import date, datetime
    today = date.today()
    if today.month == 12:
        reset_date = date(today.year + 1, 1, 1).isoformat()
    else:
        reset_date = date(today.year, today.month + 1, 1).isoformat()
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO users
           (id, email, tier, kredit_remaining, kredit_total, tokens_used_internal, reset_date, created_at)
           VALUES (?, ?, 'free', 50, 50, 0, ?, ?)""",
        (user_id, email, reset_date, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

def test_get_account_returns_name_institution(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email)
    r = c.get("/account", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert "name" in data
    assert "institution" in data
    assert data["name"] is None  # baru daftar, belum isi

def test_patch_account_updates_profile(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email)
    r = c.patch("/account/profile", json={"name": "Ahmad Fauzi", "institution": "UTM"},
                headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "Ahmad Fauzi"
    assert data["institution"] == "UTM"

def test_patch_account_then_get_returns_updated(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email)
    c.patch("/account/profile", json={"name": "Siti Noor", "institution": "UM"},
            headers={"Authorization": f"Bearer {token}"})
    r = c.get("/account", headers={"Authorization": f"Bearer {token}"})
    assert r.json()["name"] == "Siti Noor"
    assert r.json()["institution"] == "UM"
