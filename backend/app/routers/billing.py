import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user
from app.services.billing_security import verify_toyyibpay_callback
import httpx

router = APIRouter()

TOPUP_AMOUNT = 10.00   # RM10 → +200 kredit (Pro user sahaja)
TOPUP_KREDIT = 200
UPGRADE_AMOUNT = 39.00  # RM39 → Free → Pro, 500 kredit/bulan
UPGRADE_KREDIT = 500


async def _create_toyyibpay_bill(name, description, amount, return_url, callback_url, order_ref, email):
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
                "billTo": email,
                "billEmail": email,
                "billPhone": "0123456789",
                "billSplitPayment": 0,
                "billPaymentChannel": 0,
            }
        )
        resp.raise_for_status()
        result = resp.json()

    if not result or not result[0].get("BillCode"):
        raise HTTPException(500, "Gagal cipta bil pembayaran.")

    return result[0]["BillCode"]


@router.post("/topup/initiate")
async def initiate_topup(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute("SELECT tier FROM users WHERE id = ?", (user["user_id"],)).fetchone()
    if not row or row["tier"] != "pro":
        raise HTTPException(403, "Topup kredit hanya untuk pengguna Pro.")

    bill_id = str(uuid.uuid4())[:8].upper()
    order_ref = f"TOPUP-{user['user_id'][:8]}-{bill_id}"
    callback_url = settings.frontend_url.replace("/app", "") + "/api/billing/webhook"

    bill_code = await _create_toyyibpay_bill(
        name=f"ResearcherHQ Topup {bill_id}",
        description="Topup +200 Kredit Kajian",
        amount=TOPUP_AMOUNT,
        return_url=f"{settings.frontend_url.replace('/app', '')}/app/",
        callback_url=callback_url,
        order_ref=order_ref,
        email=user["email"],
    )

    with get_db() as db:
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'topup_initiated', ?, ?, ?, ?)",
            (str(uuid.uuid4()), user["user_id"], TOPUP_AMOUNT, TOPUP_KREDIT, order_ref, datetime.utcnow().isoformat())
        )

    return {"payment_url": f"https://toyyibpay.com/{bill_code}", "bill_code": bill_code}


@router.post("/upgrade/initiate")
async def initiate_upgrade(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute("SELECT tier FROM users WHERE id = ?", (user["user_id"],)).fetchone()
    if row and row["tier"] == "pro":
        raise HTTPException(400, "Akaun anda sudah Pro.")

    bill_id = str(uuid.uuid4())[:8].upper()
    order_ref = f"UPGRADE-{user['user_id'][:8]}-{bill_id}"
    callback_url = settings.frontend_url.replace("/app", "") + "/api/billing/webhook"

    bill_code = await _create_toyyibpay_bill(
        name=f"ResearcherHQ Pro {bill_id}",
        description="Naik Taraf ke Pro — 500 Kredit Kajian/bulan",
        amount=UPGRADE_AMOUNT,
        return_url=f"{settings.frontend_url.replace('/app', '')}/app/",
        callback_url=callback_url,
        order_ref=order_ref,
        email=user["email"],
    )

    with get_db() as db:
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'upgrade_initiated', ?, ?, ?, ?)",
            (str(uuid.uuid4()), user["user_id"], UPGRADE_AMOUNT, UPGRADE_KREDIT, order_ref, datetime.utcnow().isoformat())
        )

    return {"payment_url": f"https://toyyibpay.com/{bill_code}", "bill_code": bill_code}


@router.post("/webhook")
async def toyyibpay_webhook(request: Request):
    form = await request.form()
    refno = form.get("refno", "")
    status = form.get("status", "")
    order_id = form.get("order_id", "")
    received_hash = form.get("hash", "")

    if not verify_toyyibpay_callback(status, order_id, refno, received_hash):
        raise HTTPException(403, "Invalid callback signature")

    if status != "1":
        return {"status": "ignored"}

    parts = order_id.split("-")
    if len(parts) < 3 or parts[0] not in ("TOPUP", "UPGRADE"):
        return {"status": "invalid_ref"}

    bill_type = parts[0]  # "TOPUP" or "UPGRADE"
    success_event = "topup_success" if bill_type == "TOPUP" else "upgrade_success"
    initiated_event = "topup_initiated" if bill_type == "TOPUP" else "upgrade_initiated"

    with get_db() as db:
        # Idempotency
        already = db.execute(
            "SELECT id FROM billing_events WHERE reference_no = ? AND event_type = ?",
            (order_id, success_event)
        ).fetchone()
        if already:
            return {"status": "already_processed"}

        # Defense in depth — only process if we initiated this order
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

        if bill_type == "TOPUP":
            db.execute(
                "UPDATE users SET kredit_remaining = kredit_remaining + ? WHERE id = ?",
                (TOPUP_KREDIT, user["id"])
            )
            db.execute(
                "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'topup_success', ?, ?, ?, ?)",
                (str(uuid.uuid4()), user["id"], TOPUP_AMOUNT, TOPUP_KREDIT, order_id, datetime.utcnow().isoformat())
            )
        else:  # UPGRADE
            db.execute(
                "UPDATE users SET tier = 'pro', kredit_remaining = ?, kredit_total = ? WHERE id = ?",
                (UPGRADE_KREDIT, UPGRADE_KREDIT, user["id"])
            )
            db.execute(
                "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'upgrade_success', ?, ?, ?, ?)",
                (str(uuid.uuid4()), user["id"], UPGRADE_AMOUNT, UPGRADE_KREDIT, order_id, datetime.utcnow().isoformat())
            )

    return {"status": "ok"}
