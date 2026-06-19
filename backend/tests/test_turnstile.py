import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import httpx
from unittest.mock import patch, AsyncMock, MagicMock
from app.services.turnstile_service import verify_turnstile_token


def _mock_cf_response(success: bool):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"success": success})
    return mock_resp


# --- Test 1: token kosong → False tanpa network call ---
@pytest.mark.asyncio
async def test_empty_token_rejected():
    with patch("httpx.AsyncClient.post") as mock_post:
        result = await verify_turnstile_token("")
    assert result is False
    mock_post.assert_not_called()


# --- Test 2: Cloudflare balas success: true → True ---
@pytest.mark.asyncio
async def test_valid_token_accepted():
    async def fake_post(self, url, *, data, **kwargs):
        return _mock_cf_response(True)

    with patch("httpx.AsyncClient.post", new=fake_post):
        result = await verify_turnstile_token("dummy-valid-token")
    assert result is True


# --- Test 3: Cloudflare balas success: false → False ---
@pytest.mark.asyncio
async def test_invalid_token_rejected():
    async def fake_post(self, url, *, data, **kwargs):
        return _mock_cf_response(False)

    with patch("httpx.AsyncClient.post", new=fake_post):
        result = await verify_turnstile_token("dummy-invalid-token")
    assert result is False


# --- Test 4: Cloudflare timeout → fail closed (False, bukan exception) ---
@pytest.mark.asyncio
async def test_cloudflare_timeout_fails_closed():
    async def fake_post(self, url, *, data, **kwargs):
        raise httpx.TimeoutException("timeout")

    with patch("httpx.AsyncClient.post", new=fake_post):
        result = await verify_turnstile_token("any-token")
    assert result is False


# --- Test 5: /auth/request-password tanpa turnstile_token → 422 ---
def test_request_password_missing_turnstile_token_rejected(tmp_path):
    from fastapi.testclient import TestClient
    with patch("app.database._db_path", str(tmp_path / "t5.db")):
        from app.database import init_db
        init_db(str(tmp_path / "t5.db"))
        from app.main import app
        with TestClient(app) as c:
            resp = c.post("/auth/request-password", json={"email": "noturnstile@test.com"})
    assert resp.status_code == 422


# --- Test 6: /auth/request-password dengan token tak sah (mocked False) → 400, user TAK dicipta ---
def test_request_password_invalid_turnstile_token_rejected(tmp_path):
    import sqlite3
    from fastapi.testclient import TestClient
    db_path = str(tmp_path / "t6.db")
    with patch("app.database._db_path", db_path), \
         patch("app.routers.auth.verify_turnstile_token", new=AsyncMock(return_value=False)):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            resp = c.post("/auth/request-password", json={
                "email": "badtoken@test.com",
                "turnstile_token": "fake-token"
            })
        assert resp.status_code == 400
        assert "Verifikasi" in resp.json()["detail"]

        # Confirm user TIDAK dicipta dalam DB
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT id FROM users WHERE email = ?", ("badtoken@test.com",)).fetchone()
        conn.close()
        assert row is None, "User sepatutnya TIDAK dicipta bila Turnstile gagal"
