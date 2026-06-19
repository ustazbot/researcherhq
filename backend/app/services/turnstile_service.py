import httpx
from app.config import settings

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_turnstile_token(token: str, remoteip: str | None = None) -> bool:
    """
    Verify Turnstile token via Cloudflare Siteverify API.
    Token is single-use and valid for 5 minutes (Cloudflare returns
    'timeout-or-duplicate' for expired or replayed tokens).
    Fails closed — if Cloudflare is unreachable, request is rejected.
    """
    if not token:
        return False

    payload = {"secret": settings.turnstile_secret_key, "response": token}
    if remoteip:
        payload["remoteip"] = remoteip

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(TURNSTILE_VERIFY_URL, data=payload)
            resp.raise_for_status()
            result = resp.json()
    except httpx.HTTPError:
        return False

    return result.get("success", False)
