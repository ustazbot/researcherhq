import uuid
import json
from datetime import datetime
from app.database import get_db


def log_admin_action(admin_email: str, action: str, target_type: str, target_id: str, details: dict | None = None):
    with get_db() as db:
        db.execute(
            "INSERT INTO admin_action_log (id, admin_email, action, target_type, target_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), admin_email, action, target_type, target_id,
             json.dumps(details or {}), datetime.utcnow().isoformat())
        )
