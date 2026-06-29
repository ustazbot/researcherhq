import uuid
import csv
import io
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.services.admin_auth import require_admin
from app.services.admin_log import log_admin_action
from app.routers.account import _delete_user_account
from app.routers.billing import UPGRADE_KREDIT

router = APIRouter()


# ---------- STATS ----------

@router.get("/stats")
def get_stats(admin=Depends(require_admin)):
    with get_db() as db:
        row = db.execute("""
            SELECT
                COUNT(*) AS total_users,
                COUNT(CASE WHEN tier = 'free' THEN 1 END) AS free_users,
                COUNT(CASE WHEN tier = 'pro' THEN 1 END) AS pro_users,
                (SELECT COALESCE(SUM(amount), 0) FROM billing_events
                 WHERE event_type IN ('topup_success', 'upgrade_success')
                 AND created_at >= strftime('%Y-%m-01', 'now')) AS revenue_this_month,
                COUNT(CASE WHEN tier = 'pro'
                    AND DATE(subscription_start_date, '+30 days') BETWEEN DATE('now') AND DATE('now', '+7 days')
                    THEN 1 END) AS pro_expiring_7d
            FROM users
        """).fetchone()
    return {
        "total_users": row["total_users"],
        "free_users": row["free_users"],
        "pro_users": row["pro_users"],
        "revenue_this_month": float(row["revenue_this_month"]),
        "pro_expiring_7d": row["pro_expiring_7d"],
    }


# ---------- EXPORT ----------

@router.get("/export/users-csv")
def export_users_csv(tier: str, admin=Depends(require_admin)):
    if tier not in ("free", "pro"):
        raise HTTPException(status_code=400, detail="tier must be 'free' or 'pro'")
    today = datetime.utcnow().strftime("%Y%m%d")
    filename = f"rhq_users_{tier}_{today}.csv"
    with get_db() as db:
        if tier == "pro":
            rows = db.execute("""
                SELECT email, tier, kredit_remaining, kredit_total,
                       subscription_start_date,
                       DATE(subscription_start_date, '+30 days') AS subscription_expiry,
                       created_at
                FROM users WHERE tier = 'pro'
                ORDER BY created_at DESC
            """).fetchall()
            fieldnames = ["email", "tier", "kredit_remaining", "kredit_total",
                          "subscription_start_date", "subscription_expiry", "created_at"]
        else:
            rows = db.execute("""
                SELECT email, tier, kredit_remaining, kredit_total, created_at
                FROM users WHERE tier = 'free'
                ORDER BY created_at DESC
            """).fetchall()
            fieldnames = ["email", "tier", "kredit_remaining", "kredit_total", "created_at"]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(dict(row))
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- USERS ----------

@router.get("/users")
def list_users(search: Optional[str] = None, page: int = 1, page_size: int = 50, user=Depends(require_admin)):
    offset = (page - 1) * page_size
    with get_db() as db:
        if search:
            rows = db.execute(
                "SELECT id, email, tier, kredit_remaining, kredit_total, is_suspended, created_at FROM users WHERE email LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (f"%{search}%", page_size, offset)
            ).fetchall()
            total = db.execute("SELECT COUNT(*) as c FROM users WHERE email LIKE ?", (f"%{search}%",)).fetchone()["c"]
        else:
            rows = db.execute(
                "SELECT id, email, tier, kredit_remaining, kredit_total, is_suspended, created_at FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (page_size, offset)
            ).fetchall()
            total = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    return {"users": [dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


class UserUpdateBody(BaseModel):
    tier: Optional[str] = None
    kredit_remaining: Optional[int] = None
    is_suspended: Optional[bool] = None


@router.patch("/users/{target_user_id}")
def update_user(target_user_id: str, body: UserUpdateBody, admin=Depends(require_admin)):
    if body.tier is not None and body.tier not in ("free", "pro"):
        raise HTTPException(400, "Tier mesti 'free' atau 'pro'.")

    updates = {}
    if body.tier is not None:
        updates["tier"] = body.tier
    if body.kredit_remaining is not None:
        if body.kredit_remaining < 0:
            raise HTTPException(400, "kredit_remaining tak boleh negatif.")
        updates["kredit_remaining"] = body.kredit_remaining
    if body.is_suspended is not None:
        updates["is_suspended"] = 1 if body.is_suspended else 0

    if not updates:
        raise HTTPException(400, "Tiada field untuk update.")

    with get_db() as db:
        existing = db.execute("SELECT id FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "User tidak dijumpai.")
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), target_user_id))

    log_admin_action(admin["email"], "user_update", "user", target_user_id, updates)
    return {"status": "ok", "updated_fields": list(updates.keys())}


@router.post("/users/{target_user_id}/grant-pro")
def grant_pro(target_user_id: str, admin=Depends(require_admin)):
    """Naik taraf user ke Pro tanpa bayaran (pilot/influencer). Set kredit penuh Pro."""
    with get_db() as db:
        existing = db.execute("SELECT id, tier FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "User tidak dijumpai.")
        if existing["tier"] == "pro":
            raise HTTPException(400, "User sudah Pro.")
        now_date = date.today().isoformat()
        db.execute(
            """UPDATE users
               SET tier = 'pro',
                   kredit_subscription = ?,
                   kredit_total = ?,
                   kredit_remaining = ? + kredit_topup,
                   subscription_start_date = COALESCE(subscription_start_date, ?)
               WHERE id = ?""",
            (UPGRADE_KREDIT, UPGRADE_KREDIT, UPGRADE_KREDIT, now_date, target_user_id)
        )
    log_admin_action(admin["email"], "grant_pro", "user", target_user_id, {"kredit": UPGRADE_KREDIT})
    return {"status": "ok", "tier": "pro", "kredit": UPGRADE_KREDIT}


@router.delete("/users/{target_user_id}", status_code=204)
def delete_user(target_user_id: str, admin=Depends(require_admin)):
    with get_db() as db:
        existing = db.execute("SELECT id FROM users WHERE id = ?", (target_user_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "User tidak dijumpai.")
    _delete_user_account(target_user_id)
    log_admin_action(admin["email"], "user_delete", "user", target_user_id, None)
    return Response(status_code=204)


# ---------- SUPPORT REPORTS ----------

@router.get("/support-reports")
def list_support_reports(status: Optional[str] = None, admin=Depends(require_admin)):
    with get_db() as db:
        if status:
            rows = db.execute(
                "SELECT * FROM support_reports WHERE status = ? ORDER BY created_at DESC", (status,)
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM support_reports ORDER BY created_at DESC").fetchall()
    return {"reports": [dict(r) for r in rows]}


class SupportUpdateBody(BaseModel):
    status: str


@router.patch("/support-reports/{report_id}")
def update_support_report(report_id: str, body: SupportUpdateBody, admin=Depends(require_admin)):
    if body.status not in ("open", "resolved"):
        raise HTTPException(400, "status mesti 'open' atau 'resolved'.")
    with get_db() as db:
        existing = db.execute("SELECT id FROM support_reports WHERE id = ?", (report_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Laporan tidak dijumpai.")
        db.execute("UPDATE support_reports SET status = ? WHERE id = ?", (body.status, report_id))
    log_admin_action(admin["email"], "support_update", "support_report", report_id, {"status": body.status})
    return {"status": "ok"}


# ---------- BILLING (view-only + adjustment action) ----------

@router.get("/billing-events")
def list_billing_events(user_id: Optional[str] = None, admin=Depends(require_admin)):
    with get_db() as db:
        if user_id:
            rows = db.execute(
                "SELECT * FROM billing_events WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM billing_events ORDER BY created_at DESC LIMIT 200").fetchall()
    return {"events": [dict(r) for r in rows]}


class AdjustmentBody(BaseModel):
    user_id: str
    kredit_delta: int
    reason: str


@router.post("/billing-events/manual-adjustment")
def manual_credit_adjustment(body: AdjustmentBody, admin=Depends(require_admin)):
    if not body.reason or not body.reason.strip():
        raise HTTPException(400, "Reason wajib diisi untuk adjustment.")
    if body.kredit_delta == 0:
        raise HTTPException(400, "kredit_delta tak boleh 0.")

    with get_db() as db:
        target = db.execute(
            "SELECT id, kredit_subscription, kredit_topup, kredit_remaining FROM users WHERE id = ?",
            (body.user_id,)
        ).fetchone()
        if not target:
            raise HTTPException(404, "User tidak dijumpai.")

        if target["kredit_remaining"] + body.kredit_delta < 0:
            raise HTTPException(400, "Adjustment akan jadikan kredit negatif — tak dibenarkan.")
        new_sub = max(0, target["kredit_subscription"] + body.kredit_delta)
        new_balance = new_sub + target["kredit_topup"]

        db.execute(
            """UPDATE users
               SET kredit_subscription = ?, kredit_remaining = ?
               WHERE id = ?""",
            (new_sub, new_balance, body.user_id)
        )
        db.execute(
            "INSERT INTO billing_events (id, user_id, event_type, amount, kredit_added, reference_no, created_at) VALUES (?, ?, 'manual_adjustment', 0, ?, ?, ?)",
            (str(uuid.uuid4()), body.user_id, body.kredit_delta, f"ADMIN-{admin['email']}", datetime.utcnow().isoformat())
        )

    log_admin_action(
        admin["email"], "billing_adjustment", "user", body.user_id,
        {"kredit_delta": body.kredit_delta, "reason": body.reason, "new_balance": new_balance}
    )
    return {"status": "ok", "new_balance": new_balance}


# ---------- PROJECTS (view + delete sahaja) ----------

@router.get("/projects")
def list_projects(user_id: Optional[str] = None, admin=Depends(require_admin)):
    with get_db() as db:
        if user_id:
            rows = db.execute(
                "SELECT id, user_id, title, research_mode, created_at FROM projects WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, user_id, title, research_mode, created_at FROM projects ORDER BY created_at DESC LIMIT 200"
            ).fetchall()
    return {"projects": [dict(r) for r in rows]}


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, admin=Depends(require_admin)):
    with get_db() as db:
        existing = db.execute("SELECT id FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Project tidak dijumpai.")
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    log_admin_action(admin["email"], "project_delete", "project", project_id, None)
    return Response(status_code=204)


# ---------- ACTION LOG ----------

@router.get("/action-log")
def view_action_log(target_type: Optional[str] = None, target_id: Optional[str] = None, admin=Depends(require_admin)):
    with get_db() as db:
        query = "SELECT * FROM admin_action_log WHERE 1=1"
        params = []
        if target_type:
            query += " AND target_type = ?"
            params.append(target_type)
        if target_id:
            query += " AND target_id = ?"
            params.append(target_id)
        query += " ORDER BY created_at DESC LIMIT 200"
        rows = db.execute(query, params).fetchall()
    return {"log": [dict(r) for r in rows]}
