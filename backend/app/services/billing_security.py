import hashlib
import httpx
from app.config import settings


def verify_toyyibpay_callback(status: str, order_id: str, refno: str, received_hash: str) -> bool:
    """
    Validate ToyyibPay callback hash.
    Formula: MD5(userSecretKey + status + order_id + refno + "ok")
    Ref: toyyibpay.com/apireference — Callback Parameter Hash Validation
    """
    expected = hashlib.md5(
        f"{settings.toyyibpay_secret_key}{status}{order_id}{refno}ok".encode()
    ).hexdigest()
    return expected == received_hash


async def verify_toyyibpay_payment(bill_code: str) -> bool:
    """
    Defense-in-depth (security audit F1): independently confirm with ToyyibPay
    that `bill_code` is actually PAID, instead of trusting the callback alone.

    Even if the callback hash is forged or replayed (e.g. the secret key leaks),
    Pro/topup cannot be granted because ToyyibPay itself reports the true payment
    state. Fail-closed: any error, non-list response, or no successful transaction
    returns False.

    getBillTransactions returns a list of transactions; billpaymentStatus "1" = success.
    """
    if not bill_code:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://toyyibpay.com/index.php/api/getBillTransactions",
                data={
                    "userSecretKey": settings.toyyibpay_secret_key,
                    "billCode": bill_code,
                },
            )
            resp.raise_for_status()
            txns = resp.json()
    except Exception:
        return False

    if not isinstance(txns, list):
        return False
    return any(str(t.get("billpaymentStatus")) == "1" for t in txns)
