"""Task 23 — Credit model v2 tests: deduction order, reset, topup isolation."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
import hashlib
import uuid
import pytest
from datetime import date, timedelta
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt
from app.config import settings
from unittest.mock import AsyncMock


@pytest.fixture(autouse=True)
def mock_payment_verified():
    """F1: webhook confirms payment server-to-server; default to verified."""
    with patch("app.routers.billing.verify_toyyibpay_payment", new_callable=AsyncMock, return_value=True):
        yield


def _headers(user_id="user-v2", email="v2@test.com"):
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}


def _valid_hash(status, order_id, refno):
    key = settings.toyyibpay_secret_key or "testsecret"
    return hashlib.md5(f"{key}{status}{order_id}{refno}ok".encode()).hexdigest()


@pytest.fixture
def db_client(tmp_path):
    db_path = str(tmp_path / "v2.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=_headers())
            yield c, db_path


def _row(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    r = conn.execute(
        "SELECT kredit_subscription, kredit_topup, kredit_remaining FROM users WHERE id = 'user-v2'"
    ).fetchone()
    conn.close()
    return dict(r)


def _set_credits(db_path, **kwargs):
    conn = sqlite3.connect(db_path)
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    conn.execute(f"UPDATE users SET {sets} WHERE id = 'user-v2'", list(kwargs.values()))
    conn.commit()
    conn.close()


# 1. Deduction drains kredit_subscription first; kredit_topup untouched
def test_deduction_uses_subscription_first(db_client):
    c, db_path = db_client
    _set_credits(db_path, kredit_subscription=10, kredit_topup=100, kredit_remaining=110)

    from app.routers.rag import deduct_credits
    with patch("app.database._db_path", db_path):
        from app.database import get_db
        with get_db() as db:
            new_rem = deduct_credits(db, "user-v2", 8)

    r = _row(db_path)
    assert r["kredit_subscription"] == 2
    assert r["kredit_topup"] == 100
    assert r["kredit_remaining"] == 102
    assert new_rem == 102


# 2. When subscription exhausted, deducts from kredit_topup (spillover)
def test_deduction_spillover_to_topup(db_client):
    c, db_path = db_client
    _set_credits(db_path, kredit_subscription=3, kredit_topup=50, kredit_remaining=53)

    from app.routers.rag import deduct_credits
    with patch("app.database._db_path", db_path):
        from app.database import get_db
        with get_db() as db:
            new_rem = deduct_credits(db, "user-v2", 10)

    r = _row(db_path)
    assert r["kredit_subscription"] == 0
    assert r["kredit_topup"] == 43   # 50 - (10 - 3)
    assert r["kredit_remaining"] == 43


# 3. Topup webhook: kredit_topup increases; kredit_subscription unchanged
def test_topup_webhook_adds_to_topup_pool(tmp_path):
    db_path = str(tmp_path / "topup.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=_headers())

            conn = sqlite3.connect(db_path)
            conn.execute("UPDATE users SET tier = 'pro' WHERE id = 'user-v2'")
            order_ref = "TOPUP-user-v2x-AABB1122"
            conn.execute(
                "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at)"
                " VALUES (?, 'user-v2', 'topup_initiated', 10, 200, ?, '2024-01-01')",
                (str(uuid.uuid4()), order_ref)
            )
            conn.commit()
            conn.close()

            h = _valid_hash("1", order_ref, "REF001")
            r = c.post("/billing/webhook", data={
                "refno": "REF001", "status": "1",
                "order_id": order_ref, "hash": h
            })
            assert r.status_code == 200

        conn2 = sqlite3.connect(db_path)
        conn2.row_factory = sqlite3.Row
        row = conn2.execute(
            "SELECT kredit_subscription, kredit_topup, kredit_remaining FROM users WHERE id = 'user-v2'"
        ).fetchone()
        conn2.close()

    assert row["kredit_topup"] == 200
    assert row["kredit_subscription"] == 50   # untouched
    assert row["kredit_remaining"] == 250      # 50 + 200


# 4. Reset: kredit_subscription restores; kredit_topup untouched
def test_reset_restores_subscription_preserves_topup(db_client):
    c, db_path = db_client
    thirty_ago = (date.today() - timedelta(days=30)).isoformat()
    _set_credits(db_path,
                 kredit_subscription=5, kredit_topup=80, kredit_remaining=85,
                 kredit_total=50, subscription_start_date=thirty_ago)

    with patch("app.database._db_path", db_path):
        from app.services.credit_reset import reset_expired_credits
        reset_expired_credits()

    r = _row(db_path)
    assert r["kredit_subscription"] == 50   # restored to kredit_total
    assert r["kredit_topup"] == 80          # untouched
    assert r["kredit_remaining"] == 130     # 50 + 80


# 5. Upgrade webhook: sets kredit_subscription=500, subscription_start_date if NULL
def test_upgrade_webhook_sets_subscription_columns(tmp_path):
    db_path = str(tmp_path / "upgrade.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=_headers())

            conn = sqlite3.connect(db_path)
            # NULL out subscription_start_date to test COALESCE
            conn.execute("UPDATE users SET subscription_start_date = NULL WHERE id = 'user-v2'")
            order_ref = "UPGRADE-user-v2x-CCDD3344"
            conn.execute(
                "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at)"
                " VALUES (?, 'user-v2', 'upgrade_initiated', 39, 500, ?, '2024-01-01')",
                (str(uuid.uuid4()), order_ref)
            )
            conn.commit()
            conn.close()

            h = _valid_hash("1", order_ref, "REF002")
            r = c.post("/billing/webhook", data={
                "refno": "REF002", "status": "1",
                "order_id": order_ref, "hash": h
            })
            assert r.status_code == 200

        conn2 = sqlite3.connect(db_path)
        conn2.row_factory = sqlite3.Row
        row = conn2.execute(
            "SELECT kredit_subscription, kredit_topup, kredit_remaining, tier, subscription_start_date"
            " FROM users WHERE id = 'user-v2'"
        ).fetchone()
        conn2.close()

    assert row["tier"] == "pro"
    assert row["kredit_subscription"] == 500
    assert row["kredit_topup"] == 0
    assert row["kredit_remaining"] == 500
    assert row["subscription_start_date"] == date.today().isoformat()


# 6. Credits endpoint: reset_date computed from subscription_start_date + 30-day cycle
def test_credits_endpoint_reset_date_computed(db_client):
    c, db_path = db_client
    start = (date.today() - timedelta(days=10)).isoformat()
    _set_credits(db_path, subscription_start_date=start)

    with patch("app.database._db_path", db_path):
        r = c.get("/credits", headers=_headers())

    assert r.status_code == 200
    data = r.json()
    expected_reset = (date.fromisoformat(start) + timedelta(days=30)).isoformat()
    assert data["reset_date"] == expected_reset
    assert "kredit_subscription" in data
    assert "kredit_topup" in data


# 7. New user: kredit_subscription=50, kredit_topup=0, subscription_start_date=today
def test_new_user_has_correct_credit_columns(tmp_path):
    db_path = str(tmp_path / "newuser.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=_headers())

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT kredit_subscription, kredit_topup, subscription_start_date FROM users WHERE id = 'user-v2'"
        ).fetchone()
        conn.close()

    assert row["kredit_subscription"] == 50
    assert row["kredit_topup"] == 0
    assert row["subscription_start_date"] == date.today().isoformat()
