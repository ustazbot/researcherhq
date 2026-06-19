from fastapi import APIRouter, Depends, HTTPException
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()


@router.get("")
def get_credits(user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            "SELECT kredit_remaining, kredit_total, tier, reset_date FROM users WHERE id = ?",
            (user["user_id"],)
        ).fetchone()

    if not row:
        raise HTTPException(404, "Pengguna tidak dijumpai.")

    return {
        "kredit_remaining": row["kredit_remaining"],
        "kredit_total": row["kredit_total"],
        "tier": row["tier"],
        "reset_date": row["reset_date"],
    }
