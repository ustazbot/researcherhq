import uuid
import logging
from datetime import datetime, date
from fastapi import APIRouter, HTTPException, Depends, Request
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user
from app.services.billing_security import verify_toyyibpay_callback, verify_toyyibpay_payment
from app.services.bayarcash_security import (
    generate_payment_intent_checksum,
    verify_callback_checksum,
    verify_payment_intent_status,
    BAYARCASH_API_BASE,
)
import sqlite3
import httpx

logger = logging.getLogger(__name__)

router = APIRouter()

TOPUP_AMOUNT = 10.00   # RM10 → +200 kredit (Pro user sahaja)
TOPUP_KREDIT = 200
UPGRADE_AMOUNT = 39.00  # RM39 → Free → Pro, 500 kredit/bulan
UPGRADE_KREDIT = 500


async def _create_toyyibpay_bill(name, description, amount, return_url, callback_url, order_ref, payer_email, payer_name=None):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://toyyibpay.com/index.php/api/createBill",
            data={
                "userSecretKey": settings.toyyibpay_secret_key,
                "categoryCode": settings.toyyibpay_category_code,
                "billName": name,
                "billDescription": description,
                "billPriceSetting": 1,
                "billPayorInfo": 1,
                "billAmount": int(amount * 100),
                "billReturnUrl": return_url,
                "billCallbackUrl": callback_url,
                "billExternalReferenceNo": order_ref,
                "billTo": payer_email,
                "billEmail": payer_email,
                "billPhone": "0123456789",
                "billSplitPayment": 0,
                "billPaymentChannel": 0,
            }
        )
        resp.raise_for_status()
        result = resp.json()

    if not result or not result[0].get("BillCode"):
        raise HTTPException(500, "Gagal cipta bil pembayaran.")

    return f"https://toyyibpay.com/{result[0]['BillCode']}", result[0]["BillCode"]


async def _create_bayarcash_payment_intent(name, description, amount, return_url, callback_url, order_ref, payer_email, payer_name):
    # Response shape verified live 2026-07-09: {"type":"payment_intent","id":"pi_*",
    # ..., "url":"https://console.bayar.cash/payment-intent/pi_*"}
    checksum_fields = {
        "payment_channel": 1,  # 1 = FPX online banking (BayarCash v3 channel code)
        "amount": f"{amount:.2f}",
        "order_number": order_ref,
        "payer_email": payer_email,
        "payer_name": payer_name,
    }
    checksum = generate_payment_intent_checksum(checksum_fields)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{BAYARCASH_API_BASE}/payment-intents",
            data={
                "portal_key": settings.bayarcash_portal_key,
                "order_number": order_ref,
                "amount": checksum_fields["amount"],
                "payer_name": payer_name,
                "payer_email": payer_email,
                "payment_channel": checksum_fields["payment_channel"],
                "return_url": return_url,
                "callback_url": callback_url,
                "checksum": checksum,
            },
            headers={"Authorization": f"Bearer {settings.bayarcash_pat}"},
        )
        if resp.status_code >= 400:
            logger.warning("TASK5_DEBUG create-payment-intent error %s: %s", resp.status_code, resp.text[:1000])  # ponytail: remove after Task 5 verification
        resp.raise_for_status()
        result = resp.json()

    logger.warning("TASK5_DEBUG create-payment-intent response: %s", result)  # ponytail: remove after Task 5 verification

    data = result.get("data", result)
    payment_url = data.get("url")
    transaction_id = data.get("id") or data.get("transaction_id")
    if not payment_url or not transaction_id:
        raise HTTPException(500, "Gagal cipta payment intent BayarCash.")

    return payment_url, transaction_id


async def _create_payment_intent(name, description, amount, return_url, callback_url, order_ref, payer_email, payer_name):
    """Provider dispatch. TOYYIBPAY_SECRET_KEY / TOYYIBPAY_CATEGORY_CODE stay
    wired for rollback via PAYMENT_PROVIDER=toyyibpay — config swap only."""
    if settings.payment_provider == "bayarcash":
        if not settings.bayarcash_secret_key or not settings.bayarcash_pat or not settings.bayarcash_portal_key:
            raise HTTPException(500, "Konfigurasi BayarCash tidak lengkap.")
        callback_url = callback_url.replace("/billing/webhook", "/billing/webhook/bayarcash")
        return await _create_bayarcash_payment_intent(
            name, description, amount, return_url, callback_url, order_ref, payer_email, payer_name
        )
    return await _create_toyyibpay_bill(
        name, description, amount, return_url, callback_url, order_ref, payer_email, payer_name
    )


def _grant_credits_for_order(order_id: str) -> dict:
    """
    Shared success-granting logic for both the ToyyibPay and BayarCash
    webhooks. Callers MUST already have verified (a) the callback checksum
    and (b) an independent provider re-query confirming payment success
    before calling this. kredit_subscription/kredit_topup deduction order
    is untouched — this function only grants, never deducts.
    """
    parts = order_id.split("-")
    if len(parts) < 3 or parts[0] not in ("TOPUP", "UPGRADE"):
        return {"status": "invalid_ref"}

    bill_type = parts[0]
    success_event = "topup_success" if bill_type == "TOPUP" else "upgrade_success"
    initiated_event = "topup_initiated" if bill_type == "TOPUP" else "upgrade_initiated"

    with get_db() as db:
        initiated = db.execute(
            "SELECT user_id FROM billing_events WHERE reference_no = ? AND event_type = ?",
            (order_id, initiated_event)
        ).fetchone()
        if not initiated:
            return {"status": "no_matching_initiation"}

        user = db.execute(
            "SELECT id FROM users WHERE id = ?", (initiated["user_id"],)
        ).fetchone()
        if not user:
            return {"status": "user_not_found"}

        try:
            db.execute(
                "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()), user["id"], success_event,
                    TOPUP_AMOUNT if bill_type == "TOPUP" else UPGRADE_AMOUNT,
                    TOPUP_KREDIT if bill_type == "TOPUP" else UPGRADE_KREDIT,
                    order_id, datetime.utcnow().isoformat(),
                )
            )
        except sqlite3.IntegrityError:
            return {"status": "already_processed"}

        if bill_type == "TOPUP":
            db.execute(
                """UPDATE users
                   SET kredit_topup = kredit_topup + ?,
                       kredit_remaining = kredit_subscription + kredit_topup + ?
                   WHERE id = ?""",
                (TOPUP_KREDIT, TOPUP_KREDIT, user["id"])
            )
        else:  # UPGRADE
            now_date = date.today().isoformat()
            db.execute(
                """UPDATE users
                   SET tier = 'pro',
                       kredit_subscription = ?,
                       kredit_total = ?,
                       kredit_remaining = ? + kredit_topup,
                       subscription_start_date = COALESCE(subscription_start_date, ?)
                   WHERE id = ?""",
                (UPGRADE_KREDIT, UPGRADE_KREDIT, UPGRADE_KREDIT, now_date, user["id"])
            )

    return {"status": "ok"}


@router.post("/topup/initiate")
async def initiate_topup(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute("SELECT tier, name FROM users WHERE id = ?", (user["user_id"],)).fetchone()
    if not row or row["tier"] != "pro":
        raise HTTPException(403, "Topup kredit hanya untuk pengguna Pro.")

    bill_id = str(uuid.uuid4())[:8].upper()
    order_ref = f"TOPUP-{user['user_id'][:8]}-{bill_id}"
    callback_url = settings.frontend_url.replace("/app", "") + "/api/billing/webhook"

    payment_url, provider_ref = await _create_payment_intent(
        name=f"ResearcherHQ Topup {bill_id}",
        description="Topup +200 Kredit Kajian",
        amount=TOPUP_AMOUNT,
        return_url=f"{settings.frontend_url.replace('/app', '')}/app/",
        callback_url=callback_url,
        order_ref=order_ref,
        payer_email=user["email"],
        payer_name=row["name"] or user["email"],
    )

    with get_db() as db:
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'topup_initiated', ?, ?, ?, ?)",
            (str(uuid.uuid4()), user["user_id"], TOPUP_AMOUNT, TOPUP_KREDIT, order_ref, datetime.utcnow().isoformat())
        )

    return {"payment_url": payment_url, "bill_code": provider_ref}


@router.post("/upgrade/initiate")
async def initiate_upgrade(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute("SELECT tier, name FROM users WHERE id = ?", (user["user_id"],)).fetchone()
    if row and row["tier"] == "pro":
        raise HTTPException(400, "Akaun anda sudah Pro.")

    bill_id = str(uuid.uuid4())[:8].upper()
    order_ref = f"UPGRADE-{user['user_id'][:8]}-{bill_id}"
    callback_url = settings.frontend_url.replace("/app", "") + "/api/billing/webhook"

    payment_url, provider_ref = await _create_payment_intent(
        name=f"ResearcherHQ Pro {bill_id}",
        description="Naik Taraf ke Pro — 500 Kredit Kajian/bulan",
        amount=UPGRADE_AMOUNT,
        return_url=f"{settings.frontend_url.replace('/app', '')}/app/",
        callback_url=callback_url,
        order_ref=order_ref,
        payer_email=user["email"],
        payer_name=row["name"] or user["email"] if row else user["email"],
    )

    with get_db() as db:
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'upgrade_initiated', ?, ?, ?, ?)",
            (str(uuid.uuid4()), user["user_id"], UPGRADE_AMOUNT, UPGRADE_KREDIT, order_ref, datetime.utcnow().isoformat())
        )

    return {"payment_url": payment_url, "bill_code": provider_ref}


@router.post("/webhook")
async def toyyibpay_webhook(request: Request):
    form = await request.form()
    refno = form.get("refno", "")
    status = form.get("status", "")
    order_id = form.get("order_id", "")
    received_hash = form.get("hash", "")
    billcode = form.get("billcode", "")

    if not verify_toyyibpay_callback(status, order_id, refno, received_hash):
        raise HTTPException(403, "Invalid callback signature")

    if status != "1":
        return {"status": "ignored"}

    # F1 defense-in-depth: confirm the bill is truly paid with ToyyibPay
    # server-to-server. A forged/replayed callback (even with a leaked secret)
    # is rejected here because ToyyibPay reports the real payment state.
    if not await verify_toyyibpay_payment(billcode):
        return {"status": "payment_unverified"}

    return _grant_credits_for_order(order_id)


@router.post("/webhook/bayarcash")
async def bayarcash_webhook(request: Request):
    # BayarCash posts callbacks as application/x-www-form-urlencoded (verified
    # live 2026-07-09 — request.json() on it 500'd and dropped real callbacks).
    # Keep JSON accepted too for tests/manual replay.
    if "json" in request.headers.get("content-type", ""):
        data = await request.json()
    else:
        data = dict(await request.form())
    logger.warning("TASK5_DEBUG webhook payload: %s", data)  # ponytail: remove after Task 5 verification complete

    if not verify_callback_checksum(data):
        raise HTTPException(403, "Invalid callback signature")

    order_id = data.get("order_number", "")
    status = str(data.get("status", ""))

    if status != "3":
        return {"status": "ignored"}

    # Defense-in-depth — mandatory, same principle as verify_toyyibpay_payment.
    if not await verify_payment_intent_status(data.get("transaction_id", "")):
        return {"status": "payment_unverified"}

    return _grant_credits_for_order(order_id)
