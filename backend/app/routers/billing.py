import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user
import httpx

router = APIRouter()

TOPUP_AMOUNT = 10.00  # RM10
TOPUP_KREDIT = 200


@router.post("/topup/initiate")
async def initiate_topup(user=Depends(get_current_user)):
    bill_id = str(uuid.uuid4())[:8].upper()

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
                "billCallbackUrl": f"https://api.researcherhq.com/billing/webhook",
                "billExternalReferenceNo": f"TOPUP-{user['user_id'][:8]}-{bill_id}",
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
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, created_at) VALUES (?, ?, 'topup_initiated', ?, ?, ?)",
            (str(uuid.uuid4()), user["user_id"], TOPUP_AMOUNT, TOPUP_KREDIT, datetime.utcnow().isoformat())
        )

    return {
        "payment_url": f"https://toyyibpay.com/{bill_code}",
        "bill_code": bill_code
    }


@router.post("/webhook")
async def toyyibpay_webhook(request: Request):
    form = await request.form()
    ref_no = form.get("refno", "")
    status = form.get("status", "")

    if status != "1":
        return {"status": "ignored"}

    parts = ref_no.split("-")
    if len(parts) < 2:
        return {"status": "invalid_ref"}

    user_id_prefix = parts[1]

    with get_db() as db:
        user = db.execute(
            "SELECT id FROM users WHERE id LIKE ?", (f"{user_id_prefix}%",)
        ).fetchone()

        if not user:
            return {"status": "user_not_found"}

        db.execute(
            "UPDATE users SET kredit_remaining = kredit_remaining + ? WHERE id = ?",
            (TOPUP_KREDIT, user["id"])
        )
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, created_at) VALUES (?, ?, 'topup_success', ?, ?, ?)",
            (str(uuid.uuid4()), user["id"], TOPUP_AMOUNT, TOPUP_KREDIT, datetime.utcnow().isoformat())
        )

    return {"status": "ok"}
