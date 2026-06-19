import hashlib
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
