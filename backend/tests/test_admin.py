import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uuid
import sqlite3
import json
import pytest
from datetime import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient


ADMIN_EMAIL = "bos@admin.com"


def _make_user(conn, email, tier="free", kredit=50, is_suspended=0):
    uid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO users (id, email, tier, kredit_remaining, kredit_total, is_suspended, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (uid, email, tier, kredit, kredit, is_suspended, datetime.utcnow().isoformat())
    )
    conn.commit()
    return uid


def _make_project(conn, user_id, title="Test Projek"):
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO projects (id, user_id, title, research_mode, created_at) VALUES (?, ?, ?, 'general', ?)",
        (pid, user_id, title, datetime.utcnow().isoformat())
    )
    conn.commit()
    return pid


def _make_chapter(conn, project_id, title="Bab 1"):
    cid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO chapters (id, project_id, title, chapter_order, status, created_at) VALUES (?, ?, ?, 1, 'draft', ?)",
        (cid, project_id, title, datetime.utcnow().isoformat())
    )
    conn.commit()
    return cid


def _make_billing_event(conn, user_id, amount=39.0):
    eid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, created_at) VALUES (?, ?, 'topup', ?, 100, ?)",
        (eid, user_id, amount, datetime.utcnow().isoformat())
    )
    conn.commit()
    return eid


def _make_support_report(conn, user_id):
    rid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO support_reports (id, user_id, category, description, status, created_at) VALUES (?, ?, 'bug', 'test bug', 'open', ?)",
        (rid, user_id, datetime.utcnow().isoformat())
    )
    conn.commit()
    return rid


@pytest.fixture
def setup(tmp_path):
    db_path = str(tmp_path / "admin_test.db")
    from app.config import settings as app_settings
    from app.database import init_db

    with patch("app.database._db_path", db_path), \
         patch.object(app_settings, "admin_email", ADMIN_EMAIL):
        init_db(db_path)
        conn = sqlite3.connect(db_path)

        admin_id = _make_user(conn, ADMIN_EMAIL, tier="pro")
        user_id = _make_user(conn, "pengguna@test.com")
        conn.close()

        from app.services.auth_service import create_jwt
        admin_token = create_jwt({"user_id": admin_id, "email": ADMIN_EMAIL})
        user_token = create_jwt({"user_id": user_id, "email": "pengguna@test.com"})

        from app.main import app
        with TestClient(app) as c:
            yield {
                "client": c,
                "db_path": db_path,
                "admin_id": admin_id,
                "admin_token": admin_token,
                "user_id": user_id,
                "user_token": user_token,
            }


def _admin_headers(s):
    return {"Authorization": f"Bearer {s['admin_token']}"}


def _user_headers(s):
    return {"Authorization": f"Bearer {s['user_token']}"}


# --- Test 1: Non-admin email → 403 ---
def test_non_admin_gets_403(setup):
    s = setup
    r = s["client"].get("/admin/users", headers=_user_headers(s))
    assert r.status_code == 403


# --- Test 2: Admin GET /admin/users → 200 ---
def test_admin_list_users(setup):
    s = setup
    r = s["client"].get("/admin/users", headers=_admin_headers(s))
    assert r.status_code == 200
    data = r.json()
    assert "users" in data
    emails = [u["email"] for u in data["users"]]
    assert ADMIN_EMAIL in emails


# --- Test 3: PATCH is_suspended → 200, kolum updated, action log row ---
def test_patch_user_suspend(setup):
    s = setup
    r = s["client"].patch(
        f"/admin/users/{s['user_id']}",
        json={"is_suspended": True},
        headers=_admin_headers(s)
    )
    assert r.status_code == 200
    assert "is_suspended" in r.json()["updated_fields"]

    conn = sqlite3.connect(s["db_path"])
    row = conn.execute("SELECT is_suspended FROM users WHERE id = ?", (s["user_id"],)).fetchone()
    assert row[0] == 1
    log_count = conn.execute(
        "SELECT COUNT(*) FROM admin_action_log WHERE action = 'user_update' AND target_id = ?",
        (s["user_id"],)
    ).fetchone()[0]
    assert log_count == 1
    conn.close()


# --- Test 4: PATCH with invalid tier → 400 ---
def test_patch_user_invalid_tier(setup):
    s = setup
    r = s["client"].patch(
        f"/admin/users/{s['user_id']}",
        json={"tier": "vip"},
        headers=_admin_headers(s)
    )
    assert r.status_code == 400


# --- Test 5: DELETE user → PDPA cascade (user gone, projects gone, billing anonymized) ---
def test_delete_user_pdpa_cascade(setup):
    s = setup
    conn = sqlite3.connect(s["db_path"])
    proj_id = _make_project(conn, s["user_id"])
    _make_chapter(conn, proj_id)
    _make_billing_event(conn, s["user_id"])
    conn.close()

    r = s["client"].delete(f"/admin/users/{s['user_id']}", headers=_admin_headers(s))
    assert r.status_code == 204

    conn = sqlite3.connect(s["db_path"])
    user_row = conn.execute("SELECT id FROM users WHERE id = ?", (s["user_id"],)).fetchone()
    assert user_row is None, "User sepatutnya dah dipadam"

    proj_row = conn.execute("SELECT id FROM projects WHERE id = ?", (proj_id,)).fetchone()
    assert proj_row is None, "Project sepatutnya dah dipadam"

    billing_row = conn.execute(
        "SELECT user_id FROM billing_events WHERE user_id = ?", (s["user_id"],)
    ).fetchone()
    assert billing_row is None, "billing_events sepatutnya di-anonymize (user_id bukan ID asal)"

    anon_row = conn.execute(
        "SELECT COUNT(*) FROM billing_events WHERE user_id = 'deleted_user'"
    ).fetchone()[0]
    assert anon_row >= 1, "billing_events sepatutnya ada 'deleted_user' sebagai user_id"
    conn.close()


# --- Test 6: Login dengan is_suspended=1 → 403 ---
def test_login_suspended_user(setup):
    s = setup
    from app.services.auth_service import hash_password
    conn = sqlite3.connect(s["db_path"])
    conn.execute(
        "UPDATE users SET is_suspended = 1, password_hash = ? WHERE id = ?",
        (hash_password("testpass123"), s["user_id"])
    )
    conn.commit()
    conn.close()

    r = s["client"].post(
        "/auth/login",
        json={"email": "pengguna@test.com", "password": "testpass123"}
    )
    assert r.status_code == 403
    assert "digantung" in r.json()["detail"]


# --- Test 6b: Login suspended user, password SALAH → 401 (bukan 403) ---
# Detect enumeration bug: password salah tak patut dedah status suspended
def test_login_wrong_password_suspended_user_returns_401(setup):
    s = setup
    from app.services.auth_service import hash_password
    conn = sqlite3.connect(s["db_path"])
    conn.execute(
        "UPDATE users SET is_suspended = 1, password_hash = ? WHERE id = ?",
        (hash_password("betulpass999"), s["user_id"])
    )
    conn.commit()
    conn.close()

    r = s["client"].post(
        "/auth/login",
        json={"email": "pengguna@test.com", "password": "salahpass000"}
    )
    assert r.status_code == 401, f"Password salah + suspended sepatutnya 401, dapat {r.status_code}"


# --- Test 7: Manual adjustment valid → 200, kredit updated, new billing row ---
def test_manual_credit_adjustment(setup):
    s = setup
    r = s["client"].post(
        "/admin/billing-events/manual-adjustment",
        json={"user_id": s["user_id"], "kredit_delta": 20, "reason": "Goodwill credit"},
        headers=_admin_headers(s)
    )
    assert r.status_code == 200
    assert r.json()["new_balance"] == 70

    conn = sqlite3.connect(s["db_path"])
    kredit = conn.execute("SELECT kredit_remaining FROM users WHERE id = ?", (s["user_id"],)).fetchone()[0]
    assert kredit == 70

    event = conn.execute(
        "SELECT event_type, kredit_added FROM billing_events WHERE user_id = ? AND event_type = 'manual_adjustment'",
        (s["user_id"],)
    ).fetchone()
    assert event is not None
    assert event[1] == 20
    conn.close()


# --- Test 8: Manual adjustment tanpa reason → 400 ---
def test_manual_adjustment_empty_reason(setup):
    s = setup
    r = s["client"].post(
        "/admin/billing-events/manual-adjustment",
        json={"user_id": s["user_id"], "kredit_delta": 10, "reason": "   "},
        headers=_admin_headers(s)
    )
    assert r.status_code == 400


# --- Test 9: kredit_delta negatif melebihi balance → 400 ---
def test_manual_adjustment_negative_exceeds_balance(setup):
    s = setup
    r = s["client"].post(
        "/admin/billing-events/manual-adjustment",
        json={"user_id": s["user_id"], "kredit_delta": -100, "reason": "Penalti besar"},
        headers=_admin_headers(s)
    )
    assert r.status_code == 400
    assert "negatif" in r.json()["detail"]


# --- Test 10: DELETE project → 204, cascade chapters ---
def test_delete_project_cascade(setup):
    s = setup
    conn = sqlite3.connect(s["db_path"])
    proj_id = _make_project(conn, s["user_id"], "Projek Nak Padam")
    chapter_id = _make_chapter(conn, proj_id)
    conn.close()

    r = s["client"].delete(f"/admin/projects/{proj_id}", headers=_admin_headers(s))
    assert r.status_code == 204

    conn = sqlite3.connect(s["db_path"])
    conn.execute("PRAGMA foreign_keys = ON")
    proj_row = conn.execute("SELECT id FROM projects WHERE id = ?", (proj_id,)).fetchone()
    assert proj_row is None

    chapter_row = conn.execute("SELECT id FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
    assert chapter_row is None
    conn.close()


# --- Test 11: GET /admin/action-log selepas beberapa action → semua ada, terkini dulu ---
def test_action_log_records_all_actions(setup):
    s = setup
    c = s["client"]
    headers = _admin_headers(s)

    c.patch(f"/admin/users/{s['user_id']}", json={"tier": "pro"}, headers=headers)
    c.patch(f"/admin/users/{s['user_id']}", json={"kredit_remaining": 99}, headers=headers)

    conn = sqlite3.connect(s["db_path"])
    proj_id = _make_project(conn, s["user_id"])
    conn.close()
    c.delete(f"/admin/projects/{proj_id}", headers=headers)

    r = c.get("/admin/action-log", headers=headers)
    assert r.status_code == 200
    log = r.json()["log"]
    assert len(log) >= 3

    actions = [entry["action"] for entry in log]
    assert "user_update" in actions
    assert "project_delete" in actions

    # urutan terkini dulu
    timestamps = [entry["created_at"] for entry in log]
    assert timestamps == sorted(timestamps, reverse=True)


# --- Test 12: Tanpa JWT token → 401 (bukan 403) ---
def test_admin_without_jwt_returns_401(setup):
    s = setup
    endpoints = [
        ("GET", "/admin/users"),
        ("GET", "/admin/support-reports"),
        ("GET", "/admin/billing-events"),
        ("GET", "/admin/projects"),
        ("GET", "/admin/action-log"),
    ]
    for method, path in endpoints:
        r = s["client"].request(method, path)
        assert r.status_code == 401, f"{method} {path} sepatutnya 401, dapat {r.status_code}"
