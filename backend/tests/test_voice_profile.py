import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
import uuid
from datetime import datetime, date
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import init_db
from app.services.auth_service import create_jwt


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


def _reset_date():
    today = date.today()
    if today.month == 12:
        return date(today.year + 1, 1, 1).isoformat()
    return date(today.year, today.month + 1, 1).isoformat()


def _seed_user(db_path, user_id, email, tier="pro"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO users
           (id, email, tier, kredit_remaining, kredit_total, tokens_used_internal, reset_date, created_at)
           VALUES (?, ?, ?, 50, 50, 0, ?, ?)""",
        (user_id, email, tier, _reset_date(), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def _seed_project(db_path, project_id, user_id):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO projects (id, user_id, title, research_mode, created_at)
           VALUES (?, ?, 'Test Project', 'general', ?)""",
        (project_id, user_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def test_get_voice_profile_not_exists(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email)
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    r = c.get(f"/voice-profile/{pid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"exists": False}


def test_save_voice_profile_pro_user(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    r = c.post(
        f"/voice-profile/{pid}",
        json={"answers": {"q1": "Pendek & padat", "q2": "Formal tradisional"}, "sample_excerpt": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert "GAYA PENULISAN USER" in data["style_notes"]
    assert "Pendek & padat" in data["style_notes"]


def test_save_voice_profile_free_user_forbidden(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="free")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    r = c.post(
        f"/voice-profile/{pid}",
        json={"answers": {"q1": "Pendek"}, "sample_excerpt": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
    assert "Pro" in r.json()["detail"]


def test_upsert_voice_profile(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    headers = {"Authorization": f"Bearer {token}"}

    c.post(f"/voice-profile/{pid}", json={"answers": {"q1": "Pendek"}, "sample_excerpt": None}, headers=headers)
    r2 = c.post(f"/voice-profile/{pid}", json={"answers": {"q1": "Panjang & terperinci"}, "sample_excerpt": None}, headers=headers)
    assert r2.status_code == 200
    assert "Panjang & terperinci" in r2.json()["style_notes"]

    # Verify only one row in DB
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM voice_profile WHERE project_id = ?", (pid,)).fetchone()[0]
    conn.close()
    assert count == 1


def test_get_voice_profile_after_save(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    headers = {"Authorization": f"Bearer {token}"}

    c.post(f"/voice-profile/{pid}", json={"answers": {"q1": "Pendek & padat", "q3": "Elak jargon"}, "sample_excerpt": "Contoh teks."}, headers=headers)
    r = c.get(f"/voice-profile/{pid}", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["exists"] is True
    assert "Pendek & padat" in data["style_notes"]
    assert data["sample_excerpt"] == "Contoh teks."


def test_delete_project_cascades_voice_profile(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    headers = {"Authorization": f"Bearer {token}"}

    c.post(f"/voice-profile/{pid}", json={"answers": {"q1": "Pendek"}, "sample_excerpt": None}, headers=headers)

    # Delete project directly in DB (simulating cascade)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM voice_profile WHERE project_id = ?", (pid,)).fetchone()[0]
    conn.close()
    assert remaining == 0


def test_voice_profile_wrong_project(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    # Different user tries to access
    token2, uid2, email2 = make_token()
    _seed_user(db_path, uid2, email2, tier="pro")
    r = c.get(f"/voice-profile/{pid}", headers={"Authorization": f"Bearer {token2}"})
    assert r.status_code == 403
