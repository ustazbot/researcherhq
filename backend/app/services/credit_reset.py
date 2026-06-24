from datetime import date, timedelta
from app.database import get_db


def reset_expired_credits():
    today = date.today().isoformat()
    with get_db() as db:
        rows = db.execute(
            "SELECT id, tier, kredit_total, reset_date FROM users WHERE reset_date <= ?",
            (today,),
        ).fetchall()
        for row in rows:
            # Calculate next reset: first day of next month from reset_date
            reset = date.fromisoformat(row["reset_date"])
            if reset.month == 12:
                next_reset = date(reset.year + 1, 1, 1)
            else:
                next_reset = date(reset.year, reset.month + 1, 1)
            db.execute(
                "UPDATE users SET kredit_remaining = ?, reset_date = ? WHERE id = ?",
                (row["kredit_total"], next_reset.isoformat(), row["id"]),
            )
