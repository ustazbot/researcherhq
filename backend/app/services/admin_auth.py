from fastapi import Depends, HTTPException
from app.routers.auth import get_current_user
from app.config import settings


def require_admin(user=Depends(get_current_user)):
    """
    Dependency untuk semua /admin/* route. Bandingkan email dalam JWT
    terhadap ADMIN_EMAIL env var — case-insensitive.
    Tiada kolum 'role' dalam DB — hardcode satu admin sahaja.
    """
    admin_email = (settings.admin_email or "").lower()
    user_email = (user.get("email") or "").lower()
    if not admin_email or user_email != admin_email:
        raise HTTPException(403, "Akses ditolak.")
    return user
