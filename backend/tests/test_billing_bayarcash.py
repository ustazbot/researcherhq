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
