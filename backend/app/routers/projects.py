import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()

VALID_MODES = {"general", "quantitative", "qualitative", "law", "medicine"}
VALID_OUTPUT_TARGETS = {"thesis", "article", "proposal"}
VALID_DEGREE_LEVELS = {"master", "phd", "lain-lain"}
VALID_PROPOSAL_STATUSES = {"belum", "lulus"}
MAX_PROJECTS = {"free": 1, "pro": 10}

class ProjectCreate(BaseModel):
    title: str
    research_mode: str = "general"
    field: Optional[str] = None
    output_target: Optional[str] = None
    degree_level: Optional[str] = None
    proposal_status: Optional[str] = None

def _ensure_user_exists(db, user_id: str, email: str):
    """Create user row if it doesn't exist yet (auth creates it on /request-password, but tests may skip that)."""
    from datetime import date
    today = date.today()
    if today.month == 12:
        reset_date = date(today.year + 1, 1, 1).isoformat()
    else:
        reset_date = date(today.year, today.month + 1, 1).isoformat()

    db.execute(
        """INSERT OR IGNORE INTO users
           (id, email, tier, kredit_remaining, kredit_total, tokens_used_internal, reset_date, created_at)
           VALUES (?, ?, 'free', 50, 50, 0, ?, ?)""",
        (user_id, email, reset_date, datetime.utcnow().isoformat())
    )

@router.post("", status_code=201)
def create_project(body: ProjectCreate, user=Depends(get_current_user)):
    if body.research_mode not in VALID_MODES:
        raise HTTPException(400, f"Mode tidak sah. Pilih: {', '.join(sorted(VALID_MODES))}")
    if body.output_target and body.output_target not in VALID_OUTPUT_TARGETS:
        raise HTTPException(400, f"Output target tidak sah.")
    if body.degree_level and body.degree_level not in VALID_DEGREE_LEVELS:
        raise HTTPException(400, f"Tahap tidak sah.")
    if body.proposal_status and body.proposal_status not in VALID_PROPOSAL_STATUSES:
        raise HTTPException(400, f"Status proposal tidak sah.")

    with get_db() as db:
        _ensure_user_exists(db, user["user_id"], user["email"])

        user_row = db.execute("SELECT tier FROM users WHERE id = ?", (user["user_id"],)).fetchone()
        tier = user_row["tier"]

        count = db.execute(
            "SELECT COUNT(*) as c FROM projects WHERE user_id = ?", (user["user_id"],)
        ).fetchone()["c"]

        max_proj = MAX_PROJECTS.get(tier, 1)
        if count >= max_proj:
            raise HTTPException(403, f"Had projek ({max_proj}) tercapai. Naik taraf ke Pro.")

        # Pre-fill from last project if fields not supplied
        last = db.execute(
            "SELECT output_target, degree_level, proposal_status, citation_style FROM projects WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
            (user["user_id"],)
        ).fetchone()

        output_target = body.output_target or (last["output_target"] if last else "thesis")
        degree_level = body.degree_level or (last["degree_level"] if last else None)
        proposal_status = body.proposal_status or (last["proposal_status"] if last else None)
        citation_style = "APA7"  # default, editable later

        project_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        db.execute(
            """INSERT INTO projects (id, user_id, title, research_mode, field, document_set_version,
               output_target, degree_level, proposal_status, citation_style, created_at)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?)""",
            (project_id, user["user_id"], body.title, body.research_mode, body.field,
             output_target, degree_level, proposal_status, citation_style, now)
        )
        return {
            "id": project_id,
            "title": body.title,
            "research_mode": body.research_mode,
            "field": body.field,
            "output_target": output_target,
            "degree_level": degree_level,
            "proposal_status": proposal_status,
            "citation_style": citation_style,
            "document_set_version": 1,
            "created_at": now,
        }

@router.get("")
def list_projects(user=Depends(get_current_user)):
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC",
            (user["user_id"],)
        ).fetchall()
    return [dict(r) for r in rows]

@router.get("/{project_id}")
def get_project(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        ).fetchone()
    if not row:
        raise HTTPException(404, "Projek tidak dijumpai.")
    return dict(row)

@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        result = db.execute(
            "DELETE FROM projects WHERE id = ? AND user_id = ?",
            (project_id, user["user_id"])
        )
    if result.rowcount == 0:
        raise HTTPException(404, "Projek tidak dijumpai.")
