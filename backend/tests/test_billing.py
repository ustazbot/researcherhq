import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import hashlib
import uuid
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt
from app.config import settings


@pytest.fixture(autouse=True)
def mock_payment_verified():
    """F1: webhook now confirms payment server-to-server with ToyyibPay.
    Default all billing tests to a verified payment; the F1 test overrides
    this to simulate an unpaid/forged callback."""
    with patch("app.routers.billing.verify_toyyibpay_payment", new_callable=AsyncMock, return_value=True):
        yield


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


@pytest.fixture
def client_with_upgrade_initiated(tmp_path):
    """Client with a free user + one upgrade_initiated billing_event pre-seeded."""
    db_path = str(tmp_path / "upgrade_test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)

            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            order_ref = "UPGRADE-user-bil-CCDD3344"
            conn.execute(
                "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'upgrade_initiated', ?, ?, ?, datetime('now'))",
                (str(uuid.uuid4()), "user-bill", 39.0, 500, order_ref)
            )
            conn.commit()
            conn.close()
            yield c, order_ref, db_path


# --- Test 7: upgrade webhook valid → tier=pro, kredit=500 ---
def test_webhook_upgrade_sets_pro_tier(client_with_upgrade_initiated):
    c, order_ref, db_path = client_with_upgrade_initiated
    refno = "REFUPG1"
    status = "1"
    good_hash = _valid_hash(status, order_ref, refno)

    resp = c.post("/billing/webhook", data={
        "status": status, "order_id": order_ref, "refno": refno, "hash": good_hash,
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    credits = c.get("/credits", headers=make_headers()).json()
    assert credits["tier"] == "pro"
    assert credits["kredit_remaining"] == 500
    assert credits["kredit_total"] == 500


# --- Test 8: upgrade webhook idempotency → tier kekal pro, kredit tak tambah dua kali ---
def test_webhook_upgrade_idempotency(client_with_upgrade_initiated):
    c, order_ref, db_path = client_with_upgrade_initiated
    refno = "REFUPG2"
    status = "1"
    good_hash = _valid_hash(status, order_ref, refno)
    payload = {"status": status, "order_id": order_ref, "refno": refno, "hash": good_hash}

    r1 = c.post("/billing/webhook", data=payload)
    assert r1.json()["status"] == "ok"

    r2 = c.post("/billing/webhook", data=payload)
    assert r2.json()["status"] == "already_processed"

    credits = c.get("/credits", headers=make_headers()).json()
    assert credits["kredit_remaining"] == 500


# --- Test 9: topup endpoint tolak free user (403) ---
def test_topup_rejected_for_free_user(tmp_path):
    db_path = str(tmp_path / "free_topup.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)
            with patch("app.routers.billing._create_toyyibpay_bill", return_value="FAKECODE"):
                resp = c.post("/billing/topup/initiate", headers=headers)
    assert resp.status_code == 403


# --- Test 10: upgrade endpoint tolak pro user (400) ---
def test_upgrade_rejected_for_pro_user(tmp_path):
    db_path = str(tmp_path / "pro_upgrade.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)
            # Upgrade user to pro directly in DB
            import sqlite3
            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE users SET tier = 'pro' WHERE id = 'user-bill'")
            conn.commit()
            conn.close()
            with patch("app.routers.billing._create_toyyibpay_bill", return_value="FAKECODE"):
                resp = c.post("/billing/upgrade/initiate", headers=headers)
    assert resp.status_code == 400


# --- Task 17: Monthly Kredit Reset ---

def test_reset_expired_credits_resets_to_tier_allocation(tmp_path):
    # Updated for Task 23: rolling 30-day reset from subscription_start_date
    from datetime import date, timedelta
    db_path = str(tmp_path / "reset_test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)

        import sqlite3
        thirty_days_ago = (date.today() - timedelta(days=30)).isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute(
            """UPDATE users
               SET kredit_remaining = 5, kredit_subscription = 5,
                   kredit_total = 500, subscription_start_date = ?
               WHERE id = 'user-bill'""",
            (thirty_days_ago,),
        )
        conn.commit()
        conn.close()

        from app.services.credit_reset import reset_expired_credits
        reset_expired_credits()

        conn2 = sqlite3.connect(db_path)
        row = conn2.execute(
            "SELECT kredit_remaining FROM users WHERE id = 'user-bill'"
        ).fetchone()
        conn2.close()

    assert row[0] == 500


# --- Security audit F1: forged/unpaid callback rejected by server-to-server check ---
def test_webhook_rejected_when_payment_unverified(client_with_initiated):
    c, order_ref = client_with_initiated
    refno = "REFF1"
    status = "1"
    good_hash = _valid_hash(status, order_ref, refno)

    kredit_before = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]
    # Override the autouse fixture: ToyyibPay says this bill is NOT paid.
    with patch("app.routers.billing.verify_toyyibpay_payment", new_callable=AsyncMock, return_value=False):
        resp = c.post("/billing/webhook", data={
            "status": status, "order_id": order_ref, "refno": refno,
            "hash": good_hash, "billcode": "FAKEBILL",
        })
    assert resp.status_code == 200
    assert resp.json()["status"] == "payment_unverified"
    # No credits granted despite a valid hash + matching initiation.
    kredit_after = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]
    assert kredit_before == kredit_after


# --- Security audit F2: duplicate success event cannot double-grant (atomic) ---
def test_webhook_duplicate_success_blocked_by_unique_index(client_with_initiated):
    c, order_ref = client_with_initiated
    # First callback grants.
    good_hash = _valid_hash("1", order_ref, "REFF2A")
    r1 = c.post("/billing/webhook", data={
        "status": "1", "order_id": order_ref, "refno": "REFF2A",
        "hash": good_hash, "billcode": "BILL1",
    })
    assert r1.json()["status"] == "ok"
    kredit_after_first = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]

    # Second callback (different refno, same order_id) must not grant again —
    # the partial unique index makes the success insert raise IntegrityError.
    good_hash2 = _valid_hash("1", order_ref, "REFF2B")
    r2 = c.post("/billing/webhook", data={
        "status": "1", "order_id": order_ref, "refno": "REFF2B",
        "hash": good_hash2, "billcode": "BILL1",
    })
    assert r2.json()["status"] == "already_processed"
    kredit_after_second = c.get("/credits", headers=make_headers()).json()["kredit_remaining"]
    assert kredit_after_first == kredit_after_second


def test_reset_does_not_affect_unexpired_users(tmp_path):
    from datetime import date, timedelta
    db_path = str(tmp_path / "no_reset_test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)

        import sqlite3
        conn = sqlite3.connect(db_path)
        next_month = (date.today().replace(day=1) + timedelta(days=32)).replace(day=1).isoformat()
        conn.execute(
            "UPDATE users SET kredit_remaining = 10, reset_date = ? WHERE id = 'user-bill'",
            (next_month,),
        )
        conn.commit()
        conn.close()

        from app.services.credit_reset import reset_expired_credits
        reset_expired_credits()

        conn2 = sqlite3.connect(db_path)
        row = conn2.execute(
            "SELECT kredit_remaining FROM users WHERE id = 'user-bill'"
        ).fetchone()
        conn2.close()

    assert row[0] == 10
