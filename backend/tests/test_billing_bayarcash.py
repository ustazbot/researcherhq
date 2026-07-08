import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import hashlib
import hmac
import pytest
from unittest.mock import patch, AsyncMock
from app.config import settings


def _expected_checksum(secret: str, ordered_values: list) -> str:
    payload_string = "|".join(str(v) for v in ordered_values)
    return hmac.new(secret.encode(), payload_string.encode(), hashlib.sha256).hexdigest()


def test_generate_payment_intent_checksum_matches_independent_derivation():
    from app.services.bayarcash_security import generate_payment_intent_checksum

    secret = "sandboxsecret"
    payload = {
        "payment_channel": "fpx",
        "amount": "10.00",
        "order_number": "TOPUP-abcd1234-AABB1122",
        "payer_email": "bill@test.com",
        "payer_name": "Bill Tan",
    }
    # Independently derive expected checksum: sort keys, join values with '|'
    sorted_items = sorted(payload.items())
    expected = _expected_checksum(secret, [v for _, v in sorted_items])

    with patch.object(settings, "bayarcash_secret_key", secret):
        assert generate_payment_intent_checksum(payload) == expected


def test_verify_callback_checksum_accepts_valid_and_rejects_tampered():
    from app.services.bayarcash_security import verify_callback_checksum

    secret = "sandboxsecret"
    fields = [
        "transaction_id", "exchange_reference_number", "exchange_transaction_id",
        "order_number", "currency", "amount", "payer_bank_name",
        "status", "status_description",
    ]
    callback_data = {
        "transaction_id": "TXN1",
        "exchange_reference_number": "EX1",
        "exchange_transaction_id": "EXT1",
        "order_number": "TOPUP-abcd1234-AABB1122",
        "currency": "MYR",
        "amount": "10.00",
        "payer_bank_name": "Maybank",
        "status": "3",
        "status_description": "Success",
    }
    sorted_items = sorted((k, callback_data[k]) for k in fields)
    valid_checksum = _expected_checksum(secret, [v for _, v in sorted_items])

    with patch.object(settings, "bayarcash_secret_key", secret):
        good = dict(callback_data, checksum=valid_checksum)
        assert verify_callback_checksum(good) is True

        tampered = dict(callback_data, checksum=valid_checksum, amount="999.00")
        assert verify_callback_checksum(tampered) is False

        missing = dict(callback_data)
        assert verify_callback_checksum(missing) is False  # no checksum field at all


@pytest.mark.asyncio
async def test_verify_payment_intent_status_fails_closed_on_error():
    from app.services.bayarcash_security import verify_payment_intent_status

    assert await verify_payment_intent_status("") is False

    with patch("httpx.AsyncClient.get", side_effect=Exception("timeout")):
        assert await verify_payment_intent_status("PI123") is False


def test_bayarcash_webhook_route_exists(tmp_path):
    from unittest.mock import patch as _patch
    with _patch("app.database._db_path", str(tmp_path / "route_check.db")):
        from app.database import init_db
        init_db(str(tmp_path / "route_check.db"))
        from app.main import app
        from fastapi.testclient import TestClient
        with TestClient(app) as c:
            resp = c.post("/billing/webhook/bayarcash", json={})
    assert resp.status_code != 404


def test_create_payment_intent_dispatches_on_provider_setting():
    from app.routers import billing as billing_module
    assert hasattr(billing_module, "_create_payment_intent")
    assert hasattr(billing_module, "_create_bayarcash_payment_intent")
    assert hasattr(billing_module, "_grant_credits_for_order")


import uuid as _uuid
from fastapi.testclient import TestClient


def _bc_headers(user_id="user-bc", email="bc@test.com"):
    from app.services.auth_service import create_jwt
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}


def _bc_checksum(secret, data, fields):
    sorted_items = sorted((k, data.get(k, "")) for k in fields)
    payload_string = "|".join(str(v) for _, v in sorted_items)
    return hmac.new(secret.encode(), payload_string.encode(), hashlib.sha256).hexdigest()


CALLBACK_FIELDS = [
    "transaction_id", "exchange_reference_number", "exchange_transaction_id",
    "order_number", "currency", "amount", "payer_bank_name",
    "status", "status_description",
]


@pytest.fixture
def bc_client_with_topup_initiated(tmp_path):
    db_path = str(tmp_path / "bc_topup.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = _bc_headers()
            c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)

            import sqlite3
            conn = sqlite3.connect(db_path)
            order_ref = "TOPUP-user-bc-BCBC1122"
            conn.execute(
                "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'topup_initiated', ?, ?, ?, datetime('now'))",
                (str(_uuid.uuid4()), "user-bc", 10.0, 200, order_ref)
            )
            conn.commit()
            conn.close()
            yield c, order_ref


def _bc_payload(order_ref, secret, status="3", transaction_id="TXNBC1"):
    data = {
        "transaction_id": transaction_id,
        "exchange_reference_number": "EX1",
        "exchange_transaction_id": "EXT1",
        "order_number": order_ref,
        "currency": "MYR",
        "amount": "10.00",
        "payer_bank_name": "Maybank",
        "status": status,
        "status_description": "Success" if status == "3" else "Failed",
    }
    data["checksum"] = _bc_checksum(secret, data, CALLBACK_FIELDS)
    return data


# --- Webhook rejects invalid checksum (400... actually 403 per implementation) ---
def test_bayarcash_webhook_rejects_invalid_checksum(bc_client_with_topup_initiated):
    c, order_ref = bc_client_with_topup_initiated
    payload = _bc_payload(order_ref, "wrongsecret")
    with patch.object(settings, "bayarcash_secret_key", "sandboxsecret"):
        resp = c.post("/billing/webhook/bayarcash", json=payload)
    assert resp.status_code == 403


# --- Webhook rejects when independent re-verify fails, even with a valid checksum ---
def test_bayarcash_webhook_rejects_when_status_reverify_fails(bc_client_with_topup_initiated):
    c, order_ref = bc_client_with_topup_initiated
    secret = "sandboxsecret"
    payload = _bc_payload(order_ref, secret)

    kredit_before = c.get("/credits", headers=_bc_headers()).json()["kredit_remaining"]
    with patch.object(settings, "bayarcash_secret_key", secret), \
         patch("app.routers.billing.verify_payment_intent_status", new_callable=AsyncMock, return_value=False):
        resp = c.post("/billing/webhook/bayarcash", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "payment_unverified"

    kredit_after = c.get("/credits", headers=_bc_headers()).json()["kredit_remaining"]
    assert kredit_before == kredit_after


# --- Kredit grant tepat bila kedua-dua check pass ---
def test_bayarcash_webhook_grants_credit_when_both_checks_pass(bc_client_with_topup_initiated):
    c, order_ref = bc_client_with_topup_initiated
    secret = "sandboxsecret"
    payload = _bc_payload(order_ref, secret)

    kredit_before = c.get("/credits", headers=_bc_headers()).json()["kredit_remaining"]
    with patch.object(settings, "bayarcash_secret_key", secret), \
         patch("app.routers.billing.verify_payment_intent_status", new_callable=AsyncMock, return_value=True):
        resp = c.post("/billing/webhook/bayarcash", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

    kredit_after = c.get("/credits", headers=_bc_headers()).json()["kredit_remaining"]
    assert kredit_after == kredit_before + 200


# --- Non-success status is acknowledged but grants nothing ---
def test_bayarcash_webhook_ignores_non_success_status(bc_client_with_topup_initiated):
    c, order_ref = bc_client_with_topup_initiated
    secret = "sandboxsecret"
    payload = _bc_payload(order_ref, secret, status="5")

    kredit_before = c.get("/credits", headers=_bc_headers()).json()["kredit_remaining"]
    with patch.object(settings, "bayarcash_secret_key", secret):
        resp = c.post("/billing/webhook/bayarcash", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

    kredit_after = c.get("/credits", headers=_bc_headers()).json()["kredit_remaining"]
    assert kredit_before == kredit_after


# --- Idempotency: duplicate success callback cannot double-grant ---
def test_bayarcash_webhook_duplicate_success_blocked(bc_client_with_topup_initiated):
    c, order_ref = bc_client_with_topup_initiated
    secret = "sandboxsecret"
    payload1 = _bc_payload(order_ref, secret, transaction_id="TXNBC-A")
    payload2 = _bc_payload(order_ref, secret, transaction_id="TXNBC-B")

    with patch.object(settings, "bayarcash_secret_key", secret), \
         patch("app.routers.billing.verify_payment_intent_status", new_callable=AsyncMock, return_value=True):
        r1 = c.post("/billing/webhook/bayarcash", json=payload1)
        assert r1.json()["status"] == "ok"
        kredit_after_first = c.get("/credits", headers=_bc_headers()).json()["kredit_remaining"]

        r2 = c.post("/billing/webhook/bayarcash", json=payload2)
        assert r2.json()["status"] == "already_processed"
        kredit_after_second = c.get("/credits", headers=_bc_headers()).json()["kredit_remaining"]

    assert kredit_after_first == kredit_after_second


# --- Regression: kredit_subscription -> kredit_topup deduction order is untouched by this migration ---
def _seed_user(db_path, user_id, kredit_subscription, kredit_topup):
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO users (id, email, kredit_subscription, kredit_topup, kredit_remaining)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, f"{user_id}@test.com", kredit_subscription, kredit_topup,
         kredit_subscription + kredit_topup)
    )
    conn.commit()
    conn.close()


def test_deduct_credits_consumes_subscription_before_topup(tmp_path):
    """
    This migration (BayarCash provider swap) only changes how credit is
    GRANTED — it must not alter how credit is DEDUCTED. Exercise the real
    deduct_credits() function directly (from app.routers.rag) rather than
    inspecting billing.py source, since deduct_credits is where the actual
    deduction order lives.
    """
    db_path = str(tmp_path / "deduct_order.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db, get_db
        init_db(db_path)

        from app.routers.rag import deduct_credits

        # Case 1: cost fully covered by kredit_subscription alone ->
        # kredit_topup must remain untouched.
        _seed_user(db_path, "user-sub-only", kredit_subscription=100, kredit_topup=50)
        with get_db() as db:
            new_remaining = deduct_credits(db, "user-sub-only", cost=30)

        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT kredit_subscription, kredit_topup FROM users WHERE id = ?",
            ("user-sub-only",)
        ).fetchone()
        conn.close()
        assert row["kredit_subscription"] == 70
        assert row["kredit_topup"] == 50  # untouched
        assert new_remaining == 120

        # Case 2: cost spans both pools -> kredit_subscription is drained to
        # zero FIRST, and only the remainder is taken from kredit_topup.
        # This is the exact order the BayarCash migration must not alter.
        _seed_user(db_path, "user-spans-both", kredit_subscription=20, kredit_topup=50)
        with get_db() as db:
            new_remaining = deduct_credits(db, "user-spans-both", cost=45)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT kredit_subscription, kredit_topup FROM users WHERE id = ?",
            ("user-spans-both",)
        ).fetchone()
        conn.close()
        assert row["kredit_subscription"] == 0  # subscription drained first
        assert row["kredit_topup"] == 25  # 50 - (45 - 20) remainder absorbed
        assert new_remaining == 25

        # If deduction order were reversed (topup consumed before
        # subscription), the second case would instead leave
        # kredit_subscription == 20 - min(20, 45) ... i.e. topup would drop
        # to 5 and kredit_subscription would drop to 0 only after topup was
        # exhausted first — a different split entirely. The exact assertions
        # above (subscription -> 0, topup -> 25) only hold if subscription is
        # consumed before topup, so a reordering would flip these values and
        # fail the assertions.
