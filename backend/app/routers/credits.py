from datetime import date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()


@router.get("")
def get_credits(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            """SELECT kredit_remaining, kredit_subscription, kredit_topup,
                      kredit_total, tier, subscription_start_date
               FROM users WHERE id = ?""",
            (user["user_id"],)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Pengguna tidak dijumpai.")

    next_reset = None
    if row["subscription_start_date"]:
        start = date.fromisoformat(row["subscription_start_date"].split('T')[0])
        days_elapsed = (date.today() - start).days
        cycles_elapsed = max(0, days_elapsed // 30)
        next_reset = (start + timedelta(days=(cycles_elapsed + 1) * 30)).isoformat()

    return {
        "kredit_remaining": row["kredit_remaining"],
        "kredit_total": row["kredit_total"],
        "tier": row["tier"],
        "reset_date": next_reset,
        "kredit_subscription": row["kredit_subscription"],
        "kredit_topup": row["kredit_topup"],
    }
