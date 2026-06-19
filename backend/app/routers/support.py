import uuid
import httpx
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.database import get_db
from app.config import settings
from app.routers.auth import get_current_user

router = APIRouter()

VALID_CATEGORIES = {"bug", "billing", "kredit", "lain-lain"}


class ReportBody(BaseModel):
    category: str
    description: str
    project_id: Optional[str] = None


@router.post("/report", status_code=201)
async def report_issue(body: ReportBody, user=Depends(get_current_user)):
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"Kategori tidak sah: {body.category}")

    report_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()

    with get_db() as db:
        db.execute(
            """INSERT INTO support_reports (id, user_id, category, description, project_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (report_id, user["user_id"], body.category, body.description, body.project_id, now)
        )

    message = (
        f"\U0001f4e9 *Laporan Baru — ResearcherHQ*\n"
        f"ID: `{report_id[:8]}`\n"
        f"Kategori: {body.category}\n"
        f"User: `{user['email']}`\n"
        f"Keterangan: {body.description[:300]}"
    )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
            )
    except Exception:
        pass  # Jangan fail endpoint jika Telegram down

    return {"message": "Laporan diterima. Terima kasih.", "report_id": report_id}
