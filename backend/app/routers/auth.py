import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from app.database import get_db
from app.services.auth_service import (
    generate_password, hash_password, verify_password, create_jwt, decode_jwt
)
from app.services.email_service import send_password_email

router = APIRouter()
security = HTTPBearer()

DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "guerrillamail.com",
    "throwam.com", "yopmail.com", "trashmail.com", "sharklasers.com",
    "guerrillamailblock.com", "grr.la", "guerrillamail.info",
    "spam4.me", "dispostable.com", "mailnull.com"
}

class RequestPasswordBody(BaseModel):
    email: EmailStr

class LoginBody(BaseModel):
    email: EmailStr
    password: str

@router.post("/request-password")
async def request_password(body: RequestPasswordBody):
    domain = body.email.split("@")[1].lower()
    if domain in DISPOSABLE_DOMAINS:
        raise HTTPException(400, "Domain emel tidak dibenarkan.")

    pwd = generate_password()
    hashed = hash_password(pwd)

    with get_db() as db:
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?", (body.email,)
        ).fetchone()

        now = datetime.utcnow().isoformat()

        if existing:
            db.execute(
                "UPDATE users SET password_hash = ? WHERE email = ?",
                (hashed, body.email)
            )
        else:
            # Reset date = first day of next month
            from datetime import date
            today = date.today()
            if today.month == 12:
                reset_date = date(today.year + 1, 1, 1).isoformat()
            else:
                reset_date = date(today.year, today.month + 1, 1).isoformat()

            db.execute(
                """INSERT INTO users
                   (id, email, password_hash, tier, kredit_remaining, kredit_total,
                    tokens_used_internal, reset_date, created_at)
                   VALUES (?, ?, ?, 'free', 50, 50, 0, ?, ?)""",
                (str(uuid.uuid4()), body.email, hashed, reset_date, now)
            )

    await send_password_email(body.email, pwd)
    return {"message": "Kata laluan telah dihantar ke emel anda."}

@router.post("/login")
def login(body: LoginBody):
    with get_db() as db:
        user = db.execute(
            """SELECT id, email, tier, kredit_remaining, password_hash
               FROM users WHERE email = ?""",
            (body.email,)
        ).fetchone()

    if not user or not user["password_hash"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Emel atau kata laluan tidak sah.")

    token = create_jwt({"user_id": user["id"], "email": user["email"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "email": user["email"],
            "tier": user["tier"],
            "kredit_remaining": user["kredit_remaining"]
        }
    }

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = decode_jwt(credentials.credentials)
        return payload
    except ValueError:
        raise HTTPException(401, "Token tidak sah atau luput.")
