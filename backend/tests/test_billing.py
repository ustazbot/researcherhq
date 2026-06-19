import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import hashlib
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt
from app.config import settings


def make_headers(user_id="user-bill", email="bill@test.com"):
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}


def _valid_hash(status: str, order_id: str, refno: str, secret: str = "") -> str:
    key = secret or settings.toyyibpay_secret_key or "testsecret"
    return hashlib.md5(f"{key}{status}{order_id}{refno}ok".encode()).hexdigest()


@pytest.fixture
def client_with_initiated(tmp_path):
    """Client with a user + one topup_initiated billing_event pre-seeded."""
    db_path = str(tmp_path / "billing_test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            # Create user via project creation
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)

            # Seed a topup_initiated record directly
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            order_ref = "TOPUP-user-bil-AABB1122"
            conn.execute(
                "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'topup_initiated', ?, ?, ?, datetime('now'))",
                (str(uuid.uuid4()), "user-bill", 10.0, 200, order_ref)
            )
            conn.commit()
            conn.close()
            yield c, order_ref


# --- Test 1: POST webhook tanpa hash field → 403 ---
def test_webhook_missing_hash(tmp_path):
    db_path = str(tmp_path / "t1.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            resp = c.post("/billing/webhook", data={
                "status": "1",
                "order_id": "TOPUP-user-bil-AABB1122",
                "refno": "REF123"
                # no hash field
            })
    assert resp.status_code == 403


# --- Test 2: POST webhook dengan hash salah/random → 403 ---
def test_webhook_wrong_hash(tmp_path):
    db_path = str(tmp_path / "t2.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            resp = c.post("/billing/webhook", data={
                "status": "1",
                "order_id": "TOPUP-user-bil-AABB1122",
                "refno": "REF123",
                "hash": "deadbeefdeadbeefdeadbeefdeadbeef"
            })
    assert resp.status_code == 403


# --- Test 3: hash betul tapi tiada topup_initiated record → no_matching_initiation, kredit tak tambah ---
def test_webhook_valid_hash_no_initiation(tmp_path):
    db_path = str(tmp_path / "t3.db")
    order_id = "TOPUP-user-bil-ZZZZZZZZ"
    refno = "REF999"
    status = "1"
    good_hash = _valid_hash(status, order_id, refno)

    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            # Create user
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=make_headers())
            kredit_before = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]

            resp = c.post("/billing/webhook", data={
                "status": status,
                "order_id": order_id,
                "refno": refno,
                "hash": good_hash,
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "no_matching_initiation"

            kredit_after = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]
    assert kredit_before == kredit_after


# --- Test 4: webhook valid (hash betul + ada topup_initiated) → kredit +200, row topup_success ---
def test_webhook_valid_credits_added(client_with_initiated):
    c, order_ref = client_with_initiated
    refno = "REFABC"
    status = "1"
    good_hash = _valid_hash(status, order_ref, refno)

    kredit_before = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]
    resp = c.post("/billing/webhook", data={
        "status": status,
        "order_id": order_ref,
        "refno": refno,
        "hash": good_hash,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    kredit_after = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]
    assert kredit_after == kredit_before + 200


# --- Test 5: webhook sama (order_id sama) kali kedua → already_processed, kredit tak tambah lagi ---
def test_webhook_idempotency(client_with_initiated):
    c, order_ref = client_with_initiated
    refno = "REFABC"
    status = "1"
    good_hash = _valid_hash(status, order_ref, refno)

    payload = {"status": status, "order_id": order_ref, "refno": refno, "hash": good_hash}

    # First call — should succeed
    r1 = c.post("/billing/webhook", data=payload)
    assert r1.json()["status"] == "ok"

    kredit_after_first = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]

    # Second call — same order_id
    r2 = c.post("/billing/webhook", data=payload)
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_processed"

    kredit_after_second = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]
    assert kredit_after_first == kredit_after_second


# --- Test 6: verify_toyyibpay_callback hash formula match ---
def test_hash_formula_matches_toyyibpay_spec():
    """
    Verifikasi formula MD5 betul tanpa hit API sebenar.
    Guna test vector yang dibina manual dari spec ToyyibPay.
    """
    from app.services.billing_security import verify_toyyibpay_callback

    secret = "mysecretkey"
    status = "1"
    order_id = "TOPUP-abcd1234-AABB1122"
    refno = "TT123456789"

    # Build expected hash manually
    raw = f"{secret}{status}{order_id}{refno}ok"
    expected_hash = hashlib.md5(raw.encode()).hexdigest()

    with patch.object(settings, "toyyibpay_secret_key", secret):
        assert verify_toyyibpay_callback(status, order_id, refno, expected_hash) is True
        assert verify_toyyibpay_callback(status, order_id, refno, "wronghash") is False
        assert verify_toyyibpay_callback("0", order_id, refno, expected_hash) is False
