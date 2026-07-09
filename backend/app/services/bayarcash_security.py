import hmac
import hashlib
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

BAYARCASH_API_BASE = (
    "https://api.console.bayarcash-sandbox.com/v3"
    if settings.bayarcash_sandbox
    # NOTE: production domain is bayar.cash (NOT bayarcash.com — that host's TLS
    # cert doesn't match; verified live 2026-07-09, /v3/portals returns 200 here)
    else "https://api.console.bayar.cash/v3"
)


def generate_payment_intent_checksum(payload: dict) -> str:
    """
    HMAC-SHA256 checksum for the create-payment-intent request.
    Fields (sorted by key before concatenating with '|'):
    amount, order_number, payer_email, payer_name, payment_channel
    """
    sorted_payload = dict(sorted(payload.items()))
    payload_string = "|".join(str(v) for v in sorted_payload.values())
    return hmac.new(
        settings.bayarcash_secret_key.encode(),
        payload_string.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_callback_checksum(callback_data: dict) -> bool:
    """
    Verify checksum on the server-to-server callback (not the return_url redirect).
    Fields: transaction_id, exchange_reference_number, exchange_transaction_id,
    order_number, currency, amount, payer_bank_name, status, status_description
    """
    received = callback_data.get("checksum", "")
    if not received:
        return False
    fields = [
        "transaction_id", "exchange_reference_number", "exchange_transaction_id",
        "order_number", "currency", "amount", "payer_bank_name",
        "status", "status_description",
    ]
    payload = {k: callback_data.get(k, "") for k in sorted(fields)}
    payload_string = "|".join(str(v) for v in payload.values())
    expected = hmac.new(
        settings.bayarcash_secret_key.encode(),
        payload_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, received)


async def verify_payment_intent_status(transaction_id: str) -> bool:
    """
    Defense-in-depth — mirrors verify_toyyibpay_payment(). Never trust the
    callback checksum alone; re-query BayarCash directly. Fail-closed: any
    error/timeout/non-200 returns False, no credit is granted.

    Verified live 2026-07-09 (trx_Gv5eKK, RM10 FPX): callback carries
    transaction_id (trx_*), and GET /transactions/{id} returns a flat object
    with integer status; 3 = "Approved" (paid).
    """
    if not transaction_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BAYARCASH_API_BASE}/transactions/{transaction_id}",
                headers={"Authorization": f"Bearer {settings.bayarcash_pat}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("TASK5_DEBUG status re-query failed: %s", e)  # ponytail: remove after Task 5 verification complete
        return False
    logger.warning("TASK5_DEBUG status re-query response: %s", data)  # ponytail: remove after Task 5 verification complete
    return str(data.get("status")) == "3"
