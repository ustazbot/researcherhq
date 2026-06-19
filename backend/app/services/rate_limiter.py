import uuid
from datetime import datetime, timedelta
from fastapi import HTTPException, Request
from app.database import get_db


def enforce_rate_limit(scope_key: str, max_attempts: int, window_minutes: int):
    """
    Raise HTTP 429 if scope_key has reached max_attempts within the last
    window_minutes. On pass, records this attempt (caller needs no extra step).
    SQLite-backed so state is shared across multiple worker processes.
    """
    cutoff = (datetime.utcnow() - timedelta(minutes=window_minutes)).isoformat()
    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(*) as c FROM rate_limit_events WHERE scope_key = ? AND created_at > ?",
            (scope_key, cutoff)
        ).fetchone()["c"]
        if count >= max_attempts:
            raise HTTPException(429, "Terlalu banyak percubaan. Sila cuba lagi sebentar.")
        db.execute(
            "INSERT INTO rate_limit_events (id, scope_key, created_at) VALUES (?, ?, ?)",
            (str(uuid.uuid4()), scope_key, datetime.utcnow().isoformat())
        )


def get_client_ip(request: Request) -> str:
    """
    Read real client IP. Nginx is configured with 'X-Real-IP $remote_addr'
    (single trusted value). Fall back to request.client.host for local dev.
    X-Forwarded-For is intentionally NOT used — it can be spoofed by clients.
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "unknown"


def cleanup_old_rate_limit_events(older_than_hours: int = 24):
    """
    Delete records older than older_than_hours. Call opportunistically
    (e.g. 1% of requests) or via scheduled job. Not critical at MVP scale
    but prevents unbounded table growth over time.
    """
    cutoff = (datetime.utcnow() - timedelta(hours=older_than_hours)).isoformat()
    with get_db() as db:
        db.execute("DELETE FROM rate_limit_events WHERE created_at < ?", (cutoff,))
