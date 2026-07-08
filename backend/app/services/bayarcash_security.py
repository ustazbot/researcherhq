import hmac
import hashlib
import httpx
from app.config import settings

BAYARCASH_API_BASE = (
    "https://api.console.bayarcash-sandbox.com/v3"
    if settings.bayarcash_sandbox
    else "https://api.console.bayarcash.com/v3"
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


async def verify_payment_intent_status(payment_intent_id: str) -> bool:
    """
    Defense-in-depth — mirrors verify_toyyibpay_payment(). Never trust the
    callback checksum alone; re-query BayarCash directly. Fail-closed: any
    error/timeout/non-200 returns False, no credit is granted.

    ponytail: status value "3" below is unverified against a real BayarCash
    sandbox response — confirm with a live test payment intent before prod
    cutover (see Task 5 manual sandbox verification step).
    """
    if not payment_intent_id:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{BAYARCASH_API_BASE}/payment-intents/{payment_intent_id}",
                headers={"Authorization": f"Bearer {settings.bayarcash_pat}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return False
    return str(data.get("status")) in ("3", "success")
