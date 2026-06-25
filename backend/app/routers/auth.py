import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.rate_limiter import enforce_rate_limit, get_client_ip
from pydantic import BaseModel, EmailStr
from app.database import get_db
from app.services.auth_service import (
    generate_password, hash_password, verify_password, create_jwt, decode_jwt
)
from app.services.email_service import send_password_email
from app.services.turnstile_service import verify_turnstile_token

router = APIRouter()
security = HTTPBearer(auto_error=False)

DISPOSABLE_DOMAINS = {
    "mailinator.com", "tempmail.com", "guerrillamail.com",
    "throwam.com", "yopmail.com", "trashmail.com", "sharklasers.com",
    "guerrillamailblock.com", "grr.la", "guerrillamail.info",
    "spam4.me", "dispostable.com", "mailnull.com"
}

class RequestPasswordBody(BaseModel):
    email: EmailStr
    turnstile_token: str

class LoginBody(BaseModel):
    email: EmailStr
    password: str

@router.post("/request-password")
async def request_password(body: RequestPasswordBody, request: Request):
    ip = get_client_ip(request)
    enforce_rate_limit(f"request_password:ip:{ip}", max_attempts=10, window_minutes=60)
    enforce_rate_limit(f"request_password:email:{body.email.lower()}", max_attempts=3, window_minutes=15)

    if not await verify_turnstile_token(body.turnstile_token, remoteip=ip):
        raise HTTPException(400, "Verifikasi keselamatan gagal. Sila cuba lagi.")

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
                "UPDATE users SET password_hash = ?, password_is_permanent = 0 WHERE email = ?",
                (hashed, body.email)
            )
        else:
            from datetime import date
            now_date = date.today().isoformat()
            db.execute(
                """INSERT INTO users
                   (id, email, password_hash, tier, kredit_subscription, kredit_topup,
                    kredit_remaining, kredit_total, tokens_used_internal,
                    subscription_start_date, created_at)
                   VALUES (?, ?, ?, 'free', 50, 0, 50, 50, 0, ?, ?)""",
                (str(uuid.uuid4()), body.email, hashed, now_date, now)
            )

    await send_password_email(body.email, pwd)
    return {"message": "Kata laluan telah dihantar ke emel anda."}

@router.post("/login")
def login(body: LoginBody, request: Request):
    ip = get_client_ip(request)
    enforce_rate_limit(f"login:ip:{ip}", max_attempts=20, window_minutes=60)
    enforce_rate_limit(f"login:email:{body.email.lower()}", max_attempts=5, window_minutes=15)

    with get_db() as db:
        user = db.execute(
            """SELECT id, email, tier, kredit_remaining, password_hash, is_suspended
               FROM users WHERE email = ?""",
            (body.email,)
        ).fetchone()

    if not user or not user["password_hash"] or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Emel atau kata laluan tidak sah.")

    if user["is_suspended"]:
        raise HTTPException(403, "Akaun ini telah digantung. Hubungi support.")

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
    if not credentials:
        raise HTTPException(401, "Token diperlukan.")
    try:
        payload = decode_jwt(credentials.credentials)
        return payload
    except ValueError:
        raise HTTPException(401, "Token tidak sah atau luput.")

class SetPasswordBody(BaseModel):
    new_password: str

@router.post("/set-password")
def set_password(body: SetPasswordBody, user=Depends(get_current_user)):
    if len(body.new_password) < 8:
        raise HTTPException(400, "Kata laluan mesti sekurang-kurangnya 8 aksara.")

    hashed = hash_password(body.new_password)
    with get_db() as db:
        db.execute(
            "UPDATE users SET password_hash = ?, password_is_permanent = 1 WHERE id = ?",
            (hashed, user["user_id"])
        )
    return {"message": "Kata laluan tetap berjaya ditetapkan."}
