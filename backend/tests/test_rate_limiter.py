import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uuid
import sqlite3
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


from unittest.mock import AsyncMock

async def _noop_send_email(*args, **kwargs):
    pass


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "rl_test.db")
    with patch("app.database._db_path", db_path), \
         patch("app.routers.auth.send_password_email", new=_noop_send_email), \
         patch("app.routers.auth.verify_turnstile_token", new=AsyncMock(return_value=True)):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            yield c, db_path


def _req_password(client, email, ip="1.2.3.4"):
    return client.post(
        "/auth/request-password",
        json={"email": email, "turnstile_token": "dummy-always-passes"},
        headers={"x-real-ip": ip},
    )


def _login(client, email, password="wrongpass", ip="1.2.3.4"):
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"x-real-ip": ip},
    )


# --- Test 1: request-password — sama email, 4x dalam 15 minit → call ke-4 adalah 429 ---
def test_request_password_email_rate_limit(client):
    c, _ = client
    email = "victim@test.com"
    for i in range(3):
        r = _req_password(c, email)
        assert r.status_code != 429, f"Call {i+1} sepatutnya lulus"
    r4 = _req_password(c, email)
    assert r4.status_code == 429


# --- Test 2: request-password — email berbeza, sama IP, 11x dalam 1 jam → call ke-11 adalah 429 ---
def test_request_password_ip_rate_limit(client):
    c, _ = client
    ip = "5.6.7.8"
    for i in range(10):
        email = f"user{i}@different.com"
        r = _req_password(c, email, ip=ip)
        assert r.status_code != 429, f"Call {i+1} sepatutnya lulus"
    r11 = _req_password(c, "user99@different.com", ip=ip)
    assert r11.status_code == 429


# --- Test 3: login — sama email, 6x dalam 15 minit → call ke-6 adalah 429 ---
def test_login_email_rate_limit(client):
    c, _ = client
    email = "bruteforce@test.com"
    for i in range(5):
        r = _login(c, email)
        assert r.status_code != 429, f"Call {i+1} sepatutnya lulus"
    r6 = _login(c, email)
    assert r6.status_code == 429


# --- Test 4: login — window expire → call selepas window adalah 200/401 (bukan 429) ---
def test_login_rate_limit_window_expiry(tmp_path):
    db_path = str(tmp_path / "rl_expiry.db")
    with patch("app.database._db_path", db_path), \
         patch("app.routers.auth.send_password_email", new=_noop_send_email), \
         patch("app.routers.auth.verify_turnstile_token", new=AsyncMock(return_value=True)):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            email = "expiry@test.com"

            # Insert 5 stale login attempts (16 minit lalu — lepas window 15 minit)
            conn = sqlite3.connect(db_path)
            stale_ts = (datetime.utcnow() - timedelta(minutes=16)).isoformat()
            scope = f"login:email:{email}"
            for _ in range(5):
                conn.execute(
                    "INSERT INTO rate_limit_events (id, scope_key, created_at) VALUES (?, ?, ?)",
                    (str(uuid.uuid4()), scope, stale_ts)
                )
            conn.commit()
            conn.close()

            # 6th call — stale records dah expired, sepatutnya lulus (401 bukan 429)
            r = _login(c, email)
            assert r.status_code != 429, f"Sepatutnya lulus selepas window, dapat: {r.status_code}"


# --- Test 5: get_client_ip — header x-real-ip set → guna header ---
def test_get_client_ip_uses_real_ip_header():
    from app.services.rate_limiter import get_client_ip
    mock_request = MagicMock()
    mock_request.headers = {"x-real-ip": "203.0.113.42"}
    mock_request.client = MagicMock()
    mock_request.client.host = "127.0.0.1"
    assert get_client_ip(mock_request) == "203.0.113.42"


# --- Test 6: get_client_ip — tiada header → fallback ke client.host ---
def test_get_client_ip_fallback_to_client_host():
    from app.services.rate_limiter import get_client_ip
    mock_request = MagicMock()
    mock_request.headers = {}
    mock_request.client = MagicMock()
    mock_request.client.host = "192.168.1.50"
    assert get_client_ip(mock_request) == "192.168.1.50"


# --- Test 7: dua email berbeza — limit satu tak affect satu lagi ---
def test_rate_limits_are_per_scope_key(client):
    c, _ = client
    email_a = "alice@test.com"
    email_b = "bob@test.com"

    # Penuhkan limit email_a
    for _ in range(3):
        _req_password(c, email_a)
    assert _req_password(c, email_a).status_code == 429

    # email_b masih bebas
    r = _req_password(c, email_b)
    assert r.status_code != 429


# --- Test 8: cleanup_old_rate_limit_events — rekod lama padam, rekod baru kekal ---
def test_cleanup_removes_old_keeps_new(tmp_path):
    db_path = str(tmp_path / "rl_cleanup.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        old_id = str(uuid.uuid4())
        new_id = str(uuid.uuid4())
        old_ts = (datetime.utcnow() - timedelta(hours=25)).isoformat()
        new_ts = datetime.utcnow().isoformat()

        conn.execute(
            "INSERT INTO rate_limit_events (id, scope_key, created_at) VALUES (?, ?, ?)",
            (old_id, "test:old", old_ts)
        )
        conn.execute(
            "INSERT INTO rate_limit_events (id, scope_key, created_at) VALUES (?, ?, ?)",
            (new_id, "test:new", new_ts)
        )
        conn.commit()
        conn.close()

        from app.services.rate_limiter import cleanup_old_rate_limit_events
        cleanup_old_rate_limit_events(older_than_hours=24)

        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT id FROM rate_limit_events").fetchall()
        conn.close()

        ids = [r[0] for r in rows]
        assert old_id not in ids, "Rekod lama sepatutnya dah dipadam"
        assert new_id in ids, "Rekod baru sepatutnya kekal"
