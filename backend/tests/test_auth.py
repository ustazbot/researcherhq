import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import uuid
import sqlite3
from unittest.mock import patch
from fastapi.testclient import TestClient

from app.services.auth_service import (
    generate_password, hash_password, verify_password,
    create_jwt, decode_jwt
)

def test_generate_password_length():
    pwd = generate_password()
    assert len(pwd) == 8

def test_generate_password_alphanumeric():
    pwd = generate_password()
    assert pwd.isalnum()

def test_generate_password_unique():
    pwds = {generate_password() for _ in range(10)}
    assert len(pwds) > 1  # should not all be the same

def test_password_hash_verify():
    pwd = generate_password()
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed)

def test_password_wrong_rejected():
    pwd = generate_password()
    hashed = hash_password(pwd)
    assert not verify_password("wrongpass", hashed)

def test_jwt_roundtrip():
    token = create_jwt({"user_id": "abc123", "email": "test@test.com"})
    payload = decode_jwt(token)
    assert payload["user_id"] == "abc123"
    assert payload["email"] == "test@test.com"

def test_jwt_invalid_raises():
    try:
        decode_jwt("not.a.valid.token")
        assert False, "Should have raised"
    except ValueError:
        pass

def test_login_with_set_password_succeeds(tmp_path):
    """User yang set password tetap boleh login — hash tidak berubah."""
    from app.database import init_db
    from app.main import app

    db_path = str(tmp_path / "auth_test.db")
    with patch("app.database._db_path", db_path):
        init_db(db_path)
        uid = str(uuid.uuid4())
        email = "permanentpwd@test.com"
        pwd = "TestPass99"
        hashed = hash_password(pwd)
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO users (id, email, password_hash, password_is_permanent, tier,
               kredit_remaining, kredit_total, tokens_used_internal, reset_date, created_at)
               VALUES (?, ?, ?, 1, 'pro', 100, 100, 0, '2027-01-01', datetime('now'))""",
            (uid, email, hashed)
        )
        conn.commit()
        conn.close()

        with TestClient(app) as c:
            r = c.post("/auth/login", json={"email": email, "password": pwd})
        assert r.status_code == 200, f"Login gagal: {r.text}"
        assert "access_token" in r.json()

def test_pro_tier_preserved_after_init_db(tmp_path):
    """init_db() tidak reset tier user Pro yang sedia ada."""
    from app.database import init_db

    db_path = str(tmp_path / "tier_test.db")
    with patch("app.database._db_path", db_path):
        init_db(db_path)
        uid = str(uuid.uuid4())
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO users (id, email, password_hash, tier,
               kredit_remaining, kredit_total, tokens_used_internal, reset_date, created_at)
               VALUES (?, ?, 'hash', 'pro', 200, 200, 0, '2027-01-01', datetime('now'))""",
            (uid, "pro@test.com")
        )
        conn.commit()
        conn.close()

        # Panggil init_db() semula — simulasi redeploy
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT tier FROM users WHERE id = ?", (uid,)).fetchone()
        conn.close()
        assert row[0] == 'pro', f"Tier bertukar kepada '{row[0]}' selepas init_db() kedua"
