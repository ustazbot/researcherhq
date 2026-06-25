from datetime import date, timedelta
from app.database import get_db


def reset_expired_credits():
    today = date.today()
    with get_db() as db:
        rows = db.execute(
            """SELECT id, tier, kredit_total, kredit_topup, subscription_start_date
               FROM users
               WHERE subscription_start_date IS NOT NULL""",
        ).fetchall()

        for row in rows:
            start = date.fromisoformat(row["subscription_start_date"])
            days_elapsed = (today - start).days

            # Fire exactly once per 30-day cycle boundary
            if days_elapsed > 0 and days_elapsed % 30 == 0:
                new_sub = row["kredit_total"]
                db.execute(
                    """UPDATE users
                       SET kredit_subscription = ?,
                           kredit_remaining = ? + kredit_topup
                       WHERE id = ?""",
                    (new_sub, new_sub, row["id"]),
                )
