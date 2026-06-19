import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user
from app.services.billing_security import verify_toyyibpay_callback
import httpx

router = APIRouter()

TOPUP_AMOUNT = 10.00  # RM10
TOPUP_KREDIT = 200


@router.post("/topup/initiate")
async def initiate_topup(user=Depends(get_current_user)):
    bill_id = str(uuid.uuid4())[:8].upper()
    order_ref = f"TOPUP-{user['user_id'][:8]}-{bill_id}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://toyyibpay.com/index.php/api/createBill",
            data={
                "userSecretKey": settings.toyyibpay_secret_key,
                "categoryCode": settings.toyyibpay_category_code,
                "billName": f"ResearcherHQ Topup {bill_id}",
                "billDescription": "Topup +200 Kredit Kajian",
                "billPriceSetting": 1,
                "billPayorInfo": 1,
                "billAmount": int(TOPUP_AMOUNT * 100),
                "billReturnUrl": f"{settings.frontend_url}/billing/success",
                "billCallbackUrl": "https://api.researcherhq.com/billing/webhook",
                "billExternalReferenceNo": order_ref,
                "billTo": user["email"],
                "billEmail": user["email"],
                "billPhone": "0123456789",
                "billSplitPayment": 0,
                "billPaymentChannel": 0,
            }
        )
        resp.raise_for_status()
        result = resp.json()

    if not result or not result[0].get("BillCode"):
        raise HTTPException(500, "Gagal cipta bil pembayaran.")

    bill_code = result[0]["BillCode"]

    with get_db() as db:
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'topup_initiated', ?, ?, ?, ?)",
            (str(uuid.uuid4()), user["user_id"], TOPUP_AMOUNT, TOPUP_KREDIT, order_ref, datetime.utcnow().isoformat())
        )

    return {
        "payment_url": f"https://toyyibpay.com/{bill_code}",
        "bill_code": bill_code
    }


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
    if len(parts) < 3 or parts[0] != "TOPUP":
        return {"status": "invalid_ref"}

    with get_db() as db:
        # Idempotency — reject if this order_id already processed
        already = db.execute(
            "SELECT id FROM billing_events WHERE reference_no = ? AND event_type = 'topup_success'",
            (order_id,)
        ).fetchone()
        if already:
            return {"status": "already_processed"}

        # Defense in depth — only credit if we initiated this order
        initiated = db.execute(
            "SELECT user_id FROM billing_events WHERE reference_no = ? AND event_type = 'topup_initiated'",
            (order_id,)
        ).fetchone()
        if not initiated:
            return {"status": "no_matching_initiation"}

        user = db.execute(
            "SELECT id FROM users WHERE id = ?", (initiated["user_id"],)
        ).fetchone()
        if not user:
            return {"status": "user_not_found"}

        db.execute(
            "UPDATE users SET kredit_remaining = kredit_remaining + ? WHERE id = ?",
            (TOPUP_KREDIT, user["id"])
        )
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'topup_success', ?, ?, ?, ?)",
            (str(uuid.uuid4()), user["id"], TOPUP_AMOUNT, TOPUP_KREDIT, order_id, datetime.utcnow().isoformat())
        )

    return {"status": "ok"}
