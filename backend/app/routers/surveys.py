import csv
import io
import json
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.database import get_db
from app.routers.auth import get_current_user
from app.routers.rag import deduct_credits
from app.services.export_service import build_survey_docx
from app.services.rate_limiter import enforce_rate_limit
from app.services.survey_generator import generate_survey_content
from app.services import survey_import

router = APIRouter()

GENERATE_COST_FULL = 10
GENERATE_COST_SECTION = 3

# 36B publish lifecycle
COLLECTING_STATUSES = ("pilot", "published")   # structure frozen, accepting responses
PILOT_CAP_DEFAULT, PILOT_CAP_MAX = 50, 50
ACTUAL_CAP_DEFAULT, ACTUAL_CAP_MAX = 100, 1000
MAX_ACTIVE_COLLECTING = 5   # per Pro owner, pilot + published combined


def _assert_editable(db, survey_id):
    """Structure edits are forbidden while collecting responses (409)."""
    row = db.execute("SELECT status FROM surveys WHERE id=?", (survey_id,)).fetchone()
    if row and row["status"] in COLLECTING_STATUSES:
        raise HTTPException(409, "Structure is locked while collecting responses.")
    if row and row["status"] == "imported":
        raise HTTPException(409, "Imported surveys are read-only — the structure comes from the uploaded file.")


def _reject_imported(survey_row):
    """36C-4: publish lifecycle never applies to imported surveys."""
    if survey_row["status"] == "imported":
        raise HTTPException(403, "Not applicable to imported surveys.")


# ── Pydantic bodies ──────────────────────────────────────────────

class SurveyCreate(BaseModel):
    title: Optional[str] = None


class SurveyRename(BaseModel):
    title: str


class GenerateBody(BaseModel):
    scope: str = "full"  # 'full' | 'section'
    instruction: Optional[str] = None


class SectionCreate(BaseModel):
    title: str
    position: Optional[int] = None


class SectionUpdate(BaseModel):
    title: Optional[str] = None
    position: Optional[int] = None


class QuestionCreate(BaseModel):
    question_text: str
    question_type: str = "open"  # 'likert' | 'mcq' | 'open' | 'demographic'
    options: Optional[list] = None
    likert_points: Optional[int] = None
    position: Optional[int] = None


class QuestionUpdate(BaseModel):
    question_text: Optional[str] = None
    question_type: Optional[str] = None
    options: Optional[list] = None
    likert_points: Optional[int] = None
    position: Optional[int] = None
    is_reversed: Optional[bool] = None


# ── Ownership helpers ────────────────────────────────────────────

def _own_project(db, project_id, user_id):
    row = db.execute(
        "SELECT id, output_language FROM projects WHERE id=? AND user_id=?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Project not found.")
    return row


def _own_survey(db, survey_id, user_id):
    row = db.execute(
        """SELECT s.*, p.output_language FROM surveys s
           JOIN projects p ON p.id = s.project_id
           WHERE s.id=? AND p.user_id=?""",
        (survey_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Survey not found.")
    return row


def _own_section(db, section_id, user_id):
    row = db.execute(
        """SELECT sec.* FROM survey_sections sec
           JOIN surveys s ON s.id = sec.survey_id
           JOIN projects p ON p.id = s.project_id
           WHERE sec.id=? AND p.user_id=?""",
        (section_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Section not found.")
    return row


def _own_question(db, question_id, user_id):
    row = db.execute(
        """SELECT q.* FROM survey_questions q
           JOIN survey_sections sec ON sec.id = q.section_id
           JOIN surveys s ON s.id = sec.survey_id
           JOIN projects p ON p.id = s.project_id
           WHERE q.id=? AND p.user_id=?""",
        (question_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Question not found.")
    return row


def _touch_survey(db, survey_id):
    db.execute(
        "UPDATE surveys SET updated_at=? WHERE id=?",
        (datetime.utcnow().isoformat(), survey_id),
    )


def _survey_full(db, survey_row) -> dict:
    sections = db.execute(
        "SELECT * FROM survey_sections WHERE survey_id=? ORDER BY position",
        (survey_row["id"],),
    ).fetchall()
    out_sections = []
    for sec in sections:
        qs = db.execute(
            "SELECT * FROM survey_questions WHERE section_id=? ORDER BY position",
            (sec["id"],),
        ).fetchall()
        out_sections.append({
            "id": sec["id"],
            "title": sec["title"],
            "position": sec["position"],
            "questions": [
                {
                    "id": q["id"],
                    "question_text": q["question_text"],
                    "question_type": q["question_type"],
                    "options": json.loads(q["options_json"]) if q["options_json"] else None,
                    "likert_points": q["likert_points"],
                    "is_reversed": bool(q["is_reversed"]),
                    "position": q["position"],
                }
                for q in qs
            ],
        })
    keys = survey_row.keys()
    return {
        "id": survey_row["id"],
        "project_id": survey_row["project_id"],
        "title": survey_row["title"],
        "status": survey_row["status"],
        "mode": survey_row["mode"] if "mode" in keys else None,
        "share_token": survey_row["share_token"] if "share_token" in keys else None,
        "response_cap": survey_row["response_cap"] if "response_cap" in keys else None,
        "published_at": survey_row["published_at"] if "published_at" in keys else None,
        "closed_at": survey_row["closed_at"] if "closed_at" in keys else None,
        "created_at": survey_row["created_at"],
        "updated_at": survey_row["updated_at"],
        "import_filename": survey_row["import_filename"] if "import_filename" in keys else None,
        "imported_at": survey_row["imported_at"] if "imported_at" in keys else None,
        "imported_row_count": survey_row["imported_row_count"] if "imported_row_count" in keys else None,
        "sections": out_sections,
    }


def _insert_generated(db, survey_id: int, sections: list, position_offset: int = 0):
    for i, sec in enumerate(sections):
        cur = db.execute(
            "INSERT INTO survey_sections (survey_id, title, position) VALUES (?,?,?)",
            (survey_id, sec["title"], position_offset + i),
        )
        section_id = cur.lastrowid
        for j, q in enumerate(sec["questions"]):
            db.execute(
                """INSERT INTO survey_questions
                   (section_id, question_text, question_type, options_json, likert_points, is_reversed, position)
                   VALUES (?,?,?,?,?,0,?)""",
                (
                    section_id,
                    q["question_text"],
                    q["question_type"],
                    json.dumps(q["options"], ensure_ascii=False) if q.get("options") else None,
                    q.get("likert_points"),
                    j,
                ),
            )


# ── Survey CRUD ──────────────────────────────────────────────────

@router.post("/projects/{project_id}/surveys", status_code=201)
def create_survey(project_id: str, body: SurveyCreate, user=Depends(get_current_user)):
    with get_db() as db:
        _own_project(db, project_id, user["user_id"])
        # 36B §1 — Survey module is Pro-only (retroactive patch)
        tier_row = db.execute("SELECT tier FROM users WHERE id=?", (user["user_id"],)).fetchone()
        if not tier_row or tier_row["tier"] != "pro":
            raise HTTPException(403, "The Survey module is available on the Pro plan only.")
        now = datetime.utcnow().isoformat()
        cur = db.execute(
            "INSERT INTO surveys (project_id, title, status, created_at, updated_at) VALUES (?,?,'draft',?,?)",
            (project_id, body.title or "Survey", now, now),
        )
        sid = cur.lastrowid
    return {"id": sid, "project_id": project_id, "title": body.title or "Survey", "status": "draft"}


@router.get("/projects/{project_id}/surveys")
def list_surveys(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        _own_project(db, project_id, user["user_id"])
        rows = db.execute(
            "SELECT * FROM surveys WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/surveys/{survey_id}")
def get_survey(survey_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        return _survey_full(db, survey)


@router.patch("/surveys/{survey_id}")
def rename_survey(survey_id: int, body: SurveyRename, user=Depends(get_current_user)):
    with get_db() as db:
        _own_survey(db, survey_id, user["user_id"])
        db.execute("UPDATE surveys SET title=? WHERE id=?", (body.title, survey_id))
        _touch_survey(db, survey_id)
    return {"id": survey_id, "title": body.title}


@router.delete("/surveys/{survey_id}", status_code=204)
def delete_survey(survey_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        _own_survey(db, survey_id, user["user_id"])
        db.execute("DELETE FROM surveys WHERE id=?", (survey_id,))
        # sections & questions cascade via FK


# ── External data import (36C-4) ─────────────────────────────────

class ImportColumnMapping(BaseModel):
    column_name: str
    action: str  # 'skip' | 'question'
    question_type: Optional[str] = None
    likert_points: Optional[int] = None
    is_reversed: Optional[bool] = False
    override_pii_warning: Optional[bool] = False


class ImportConfirmBody(BaseModel):
    preview_token: str
    survey_title: Optional[str] = None
    is_pilot: bool = False
    column_mappings: list[ImportColumnMapping]


def _require_pro(db, user_id):
    tier_row = db.execute("SELECT tier FROM users WHERE id=?", (user_id,)).fetchone()
    if not tier_row or tier_row["tier"] != "pro":
        raise HTTPException(403, "The Survey module is available on the Pro plan only.")


@router.post("/projects/{project_id}/surveys/import/preview")
async def import_preview(project_id: str, file: UploadFile = File(...), user=Depends(get_current_user)):
    with get_db() as db:
        _own_project(db, project_id, user["user_id"])
        _require_pro(db, user["user_id"])
    # VPS protection: parsing is the expensive step — 10 imports/day per owner
    enforce_rate_limit(f"survey_import:{user['user_id']}", max_attempts=10, window_minutes=1440)
    data = await file.read()
    df = survey_import.parse_upload(file.filename or "", data)
    token = survey_import.cache_preview(user["user_id"], file.filename or "upload", df)
    return survey_import.build_preview_response(token, file.filename or "upload", df)


@router.post("/projects/{project_id}/surveys/import/confirm", status_code=201)
def import_confirm(project_id: str, body: ImportConfirmBody, user=Depends(get_current_user)):
    with get_db() as db:
        _own_project(db, project_id, user["user_id"])
        _require_pro(db, user["user_id"])
        filename, df = survey_import.get_preview(body.preview_token, user["user_id"])
        questions = survey_import.validate_mappings(
            df, [m.dict() for m in body.column_mappings])
        summary = survey_import.create_imported_survey(
            db, project_id, body.survey_title or filename, body.is_pilot,
            filename, df, questions)
    survey_import.drop_preview(body.preview_token)
    return summary


# ── AI Generation ────────────────────────────────────────────────

@router.post("/surveys/{survey_id}/generate")
async def generate_survey(survey_id: int, body: GenerateBody, user=Depends(get_current_user)):
    if body.scope not in ("full", "section"):
        raise HTTPException(400, "Invalid scope. Use 'full' or 'section'.")
    cost = GENERATE_COST_FULL if body.scope == "full" else GENERATE_COST_SECTION

    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        _assert_editable(db, survey_id)
        project_id = survey["project_id"]
        output_language = survey["output_language"] or "bm"

        doc_count = db.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE project_id=?", (project_id,)
        ).fetchone()["c"]
        if doc_count == 0:
            raise HTTPException(
                400,
                "No documents in this project. Upload your working paper or proposal first — the instrument is generated from your project documents.",
            )

        kredit = db.execute(
            "SELECT kredit_remaining FROM users WHERE id=?", (user["user_id"],)
        ).fetchone()
        if not kredit or kredit["kredit_remaining"] < cost:
            raise HTTPException(402, "Insufficient Research Credits.")

    # LLM call outside DB transaction — can take tens of seconds
    try:
        generated = await generate_survey_content(
            project_id=project_id,
            output_language=output_language,
            scope=body.scope,
            instruction=body.instruction or "",
        )
    except ValueError as e:
        # parse failed after retry — NO credit deduction
        raise HTTPException(502, f"Generation failed: {e}. No credits were deducted — please try again.")

    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        if body.scope == "full":
            # REPLACE existing content (frontend confirms before calling)
            db.execute(
                "DELETE FROM survey_sections WHERE survey_id=?", (survey_id,)
            )
            _insert_generated(db, survey_id, generated["sections"])
        else:
            max_pos = db.execute(
                "SELECT COALESCE(MAX(position), -1) AS m FROM survey_sections WHERE survey_id=?",
                (survey_id,),
            ).fetchone()["m"]
            _insert_generated(db, survey_id, generated["sections"], position_offset=max_pos + 1)

        # kredit ditolak HANYA selepas generation berjaya. F3: kredit boleh
        # habis antara pre-check dan sini (TOCTOU) — pulangkan 402, bukan 500,
        # dan biar transaksi rollback supaya sections yang di-insert dibuang.
        try:
            new_kredit = deduct_credits(db, user["user_id"], cost)
        except ValueError:
            raise HTTPException(402, "Insufficient Research Credits.")
        _touch_survey(db, survey_id)
        result = _survey_full(db, _own_survey(db, survey_id, user["user_id"]))

    result["kredit_remaining"] = new_kredit
    result["kredit_used"] = cost
    return result


# ── Section CRUD ─────────────────────────────────────────────────

@router.post("/surveys/{survey_id}/sections", status_code=201)
def create_section(survey_id: int, body: SectionCreate, user=Depends(get_current_user)):
    with get_db() as db:
        _own_survey(db, survey_id, user["user_id"])
        _assert_editable(db, survey_id)
        if body.position is None:
            max_pos = db.execute(
                "SELECT COALESCE(MAX(position), -1) AS m FROM survey_sections WHERE survey_id=?",
                (survey_id,),
            ).fetchone()["m"]
            position = max_pos + 1
        else:
            position = body.position
        cur = db.execute(
            "INSERT INTO survey_sections (survey_id, title, position) VALUES (?,?,?)",
            (survey_id, body.title, position),
        )
        _touch_survey(db, survey_id)
        sec_id = cur.lastrowid
    return {"id": sec_id, "survey_id": survey_id, "title": body.title, "position": position}


@router.patch("/sections/{section_id}")
def update_section(section_id: int, body: SectionUpdate, user=Depends(get_current_user)):
    with get_db() as db:
        sec = _own_section(db, section_id, user["user_id"])
        _assert_editable(db, sec["survey_id"])
        new_title = body.title if body.title is not None else sec["title"]
        new_pos = body.position if body.position is not None else sec["position"]
        db.execute(
            "UPDATE survey_sections SET title=?, position=? WHERE id=?",
            (new_title, new_pos, section_id),
        )
        _touch_survey(db, sec["survey_id"])
    return {"id": section_id, "title": new_title, "position": new_pos}


@router.delete("/sections/{section_id}", status_code=204)
def delete_section(section_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        sec = _own_section(db, section_id, user["user_id"])
        _assert_editable(db, sec["survey_id"])
        db.execute("DELETE FROM survey_sections WHERE id=?", (section_id,))
        _touch_survey(db, sec["survey_id"])


# ── Question CRUD ────────────────────────────────────────────────

@router.post("/sections/{section_id}/questions", status_code=201)
def create_question(section_id: int, body: QuestionCreate, user=Depends(get_current_user)):
    if body.question_type not in ("likert", "mcq", "open", "demographic"):
        raise HTTPException(400, "Invalid question type.")
    with get_db() as db:
        sec = _own_section(db, section_id, user["user_id"])
        _assert_editable(db, sec["survey_id"])
        if body.position is None:
            max_pos = db.execute(
                "SELECT COALESCE(MAX(position), -1) AS m FROM survey_questions WHERE section_id=?",
                (section_id,),
            ).fetchone()["m"]
            position = max_pos + 1
        else:
            position = body.position
        cur = db.execute(
            """INSERT INTO survey_questions
               (section_id, question_text, question_type, options_json, likert_points, is_reversed, position)
               VALUES (?,?,?,?,?,0,?)""",
            (
                section_id,
                body.question_text,
                body.question_type,
                json.dumps(body.options, ensure_ascii=False) if body.options else None,
                body.likert_points,
                position,
            ),
        )
        _touch_survey(db, sec["survey_id"])
        q_id = cur.lastrowid
    return {"id": q_id, "section_id": section_id, "question_text": body.question_text,
            "question_type": body.question_type, "position": position}


@router.patch("/questions/{question_id}")
def update_question(question_id: int, body: QuestionUpdate, user=Depends(get_current_user)):
    if body.question_type is not None and body.question_type not in ("likert", "mcq", "open", "demographic"):
        raise HTTPException(400, "Invalid question type.")
    with get_db() as db:
        q = _own_question(db, question_id, user["user_id"])
        sec_edit = _own_section(db, q["section_id"], user["user_id"])
        _assert_editable(db, sec_edit["survey_id"])
        new_text = body.question_text if body.question_text is not None else q["question_text"]
        new_type = body.question_type if body.question_type is not None else q["question_type"]
        new_options = json.dumps(body.options, ensure_ascii=False) if body.options is not None else q["options_json"]
        new_points = body.likert_points if body.likert_points is not None else q["likert_points"]
        new_pos = body.position if body.position is not None else q["position"]
        new_rev = int(body.is_reversed) if body.is_reversed is not None else q["is_reversed"]
        db.execute(
            """UPDATE survey_questions
               SET question_text=?, question_type=?, options_json=?, likert_points=?, position=?, is_reversed=?
               WHERE id=?""",
            (new_text, new_type, new_options, new_points, new_pos, new_rev, question_id),
        )
        sec = _own_section(db, q["section_id"], user["user_id"])
        _touch_survey(db, sec["survey_id"])
    return {"id": question_id, "question_text": new_text, "question_type": new_type,
            "position": new_pos, "is_reversed": bool(new_rev)}


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        q = _own_question(db, question_id, user["user_id"])
        sec = _own_section(db, q["section_id"], user["user_id"])
        _assert_editable(db, sec["survey_id"])
        db.execute("DELETE FROM survey_questions WHERE id=?", (question_id,))
        _touch_survey(db, sec["survey_id"])


# ── Export ───────────────────────────────────────────────────────

@router.get("/surveys/{survey_id}/export/docx")
def export_survey_docx(survey_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        full = _survey_full(db, survey)

    docx_bytes = build_survey_docx(full["title"], full["sections"])
    safe_name = "".join(ch for ch in full["title"] if ch.isalnum() or ch in " -_").strip() or "survey"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.docx"'},
    )


# ── Publish lifecycle (36B) ──────────────────────────────────────

class PublishBody(BaseModel):
    mode: str  # 'pilot' | 'actual'
    response_cap: Optional[int] = None


def _count_active_collecting(db, user_id: str, exclude_survey_id: int = None) -> int:
    q = """SELECT COUNT(*) AS c FROM surveys s
           JOIN projects p ON p.id = s.project_id
           WHERE p.user_id = ? AND s.status IN ('pilot','published')"""
    params = [user_id]
    if exclude_survey_id is not None:
        q += " AND s.id != ?"
        params.append(exclude_survey_id)
    return db.execute(q, params).fetchone()["c"]


def _clamp_cap(mode: str, requested: Optional[int]) -> int:
    if mode == "pilot":
        default, cap_max = PILOT_CAP_DEFAULT, PILOT_CAP_MAX
    else:
        default, cap_max = ACTUAL_CAP_DEFAULT, ACTUAL_CAP_MAX
    if requested is None:
        return default
    return max(1, min(int(requested), cap_max))


@router.post("/surveys/{survey_id}/publish")
def publish_survey(survey_id: int, body: PublishBody, user=Depends(get_current_user)):
    if body.mode not in ("pilot", "actual"):
        raise HTTPException(400, "Invalid mode. Use 'pilot' or 'actual'.")
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        _reject_imported(survey)
        if survey["status"] != "draft":
            raise HTTPException(409, "Only a draft survey can be published.")

        # Must have at least 1 section AND 1 question
        q_count = db.execute(
            """SELECT COUNT(*) AS c FROM survey_questions q
               JOIN survey_sections sec ON sec.id = q.section_id
               WHERE sec.survey_id = ?""",
            (survey_id,),
        ).fetchone()["c"]
        if q_count == 0:
            raise HTTPException(400, "A survey must have at least one section and one question.")

        # Tier limit: max 5 active collecting per owner
        if _count_active_collecting(db, user["user_id"]) >= MAX_ACTIVE_COLLECTING:
            raise HTTPException(403, f"Limit of {MAX_ACTIVE_COLLECTING} active surveys reached. Close one first.")

        cap = _clamp_cap(body.mode, body.response_cap)
        new_status = "pilot" if body.mode == "pilot" else "published"
        token = survey["share_token"] or secrets.token_urlsafe(16)
        now = datetime.utcnow().isoformat()
        db.execute(
            """UPDATE surveys
               SET status=?, mode=?, share_token=?, response_cap=?, published_at=?, closed_at=NULL, updated_at=?
               WHERE id=?""",
            (new_status, body.mode, token, cap, now, now, survey_id),
        )
        result = _survey_full(db, _own_survey(db, survey_id, user["user_id"]))
    return result


@router.post("/surveys/{survey_id}/close")
def close_survey(survey_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        _reject_imported(survey)
        if survey["status"] == "pilot":
            new_status = "pilot_closed"
        elif survey["status"] == "published":
            new_status = "closed"
        else:
            raise HTTPException(409, "This survey is not collecting responses.")
        now = datetime.utcnow().isoformat()
        db.execute("UPDATE surveys SET status=?, closed_at=?, updated_at=? WHERE id=?",
                   (new_status, now, now, survey_id))
        return _survey_full(db, _own_survey(db, survey_id, user["user_id"]))


@router.post("/surveys/{survey_id}/reopen")
def reopen_survey(survey_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        _reject_imported(survey)
        if survey["status"] == "pilot_closed":
            new_status = "pilot"
        elif survey["status"] == "closed":
            new_status = "published"
        else:
            raise HTTPException(409, "Only a closed survey can be reopened.")
        # Tier limit applies when re-entering a collecting state
        if _count_active_collecting(db, user["user_id"], exclude_survey_id=survey_id) >= MAX_ACTIVE_COLLECTING:
            raise HTTPException(403, f"Limit of {MAX_ACTIVE_COLLECTING} active surveys reached.")
        now = datetime.utcnow().isoformat()
        db.execute("UPDATE surveys SET status=?, closed_at=NULL, updated_at=? WHERE id=?",
                   (new_status, now, survey_id))
        return _survey_full(db, _own_survey(db, survey_id, user["user_id"]))


@router.post("/surveys/{survey_id}/unlock")
def unlock_survey(survey_id: int, user=Depends(get_current_user)):
    """pilot_closed → draft. Pilot responses are kept (is_pilot=1) for Fasa C."""
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        _reject_imported(survey)
        if survey["status"] != "pilot_closed":
            raise HTTPException(409, "Only a closed pilot survey can be unlocked for editing.")
        now = datetime.utcnow().isoformat()
        db.execute("UPDATE surveys SET status='draft', mode=NULL, updated_at=? WHERE id=?",
                   (now, survey_id))
        return _survey_full(db, _own_survey(db, survey_id, user["user_id"]))


@router.post("/surveys/{survey_id}/unpublish")
def unpublish_survey(survey_id: int, user=Depends(get_current_user)):
    """published → draft, only if 0 actual responses."""
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        _reject_imported(survey)
        if survey["status"] != "published":
            raise HTTPException(409, "Only an active actual survey can be unpublished.")
        actual_count = db.execute(
            "SELECT COUNT(*) AS c FROM survey_responses WHERE survey_id=? AND is_pilot=0",
            (survey_id,),
        ).fetchone()["c"]
        if actual_count > 0:
            raise HTTPException(409, "This survey has actual responses. Delete all actual responses before unpublishing.")
        now = datetime.utcnow().isoformat()
        db.execute("UPDATE surveys SET status='draft', mode=NULL, updated_at=? WHERE id=?",
                   (now, survey_id))
        return _survey_full(db, _own_survey(db, survey_id, user["user_id"]))


# ── Response dashboard (36B) ─────────────────────────────────────

def _type_filter(rtype: str):
    if rtype == "pilot":
        return " AND is_pilot=1"
    if rtype == "actual":
        return " AND is_pilot=0"
    return ""


@router.get("/surveys/{survey_id}/responses")
def list_responses(survey_id: int, type: str = "all", page: int = 1, page_size: int = 50,
                   user=Depends(get_current_user)):
    if type not in ("pilot", "actual", "all"):
        raise HTTPException(400, "type must be pilot|actual|all.")
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        pilot = db.execute("SELECT COUNT(*) AS c FROM survey_responses WHERE survey_id=? AND is_pilot=1", (survey_id,)).fetchone()["c"]
        actual = db.execute("SELECT COUNT(*) AS c FROM survey_responses WHERE survey_id=? AND is_pilot=0", (survey_id,)).fetchone()["c"]
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        last7 = db.execute(
            "SELECT COUNT(*) AS c FROM survey_responses WHERE survey_id=? AND submitted_at > ?" + _type_filter(type),
            (survey_id, week_ago),
        ).fetchone()["c"]
        rows = db.execute(
            "SELECT id, submitted_at, is_pilot FROM survey_responses WHERE survey_id=?" + _type_filter(type)
            + " ORDER BY submitted_at DESC LIMIT ? OFFSET ?",
            (survey_id, page_size, (page - 1) * page_size),
        ).fetchall()
    return {
        "counts": {"pilot": pilot, "actual": actual, "all": pilot + actual},
        "last_7_days": last7,
        "cap": survey["response_cap"],
        "mode": survey["mode"],
        "status": survey["status"],
        "page": page,
        "responses": [{"id": r["id"], "submitted_at": r["submitted_at"], "is_pilot": bool(r["is_pilot"])} for r in rows],
    }


@router.get("/surveys/{survey_id}/responses/{response_id}")
def get_response(survey_id: int, response_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        _own_survey(db, survey_id, user["user_id"])
        resp = db.execute(
            "SELECT id, submitted_at, is_pilot FROM survey_responses WHERE id=? AND survey_id=?",
            (response_id, survey_id),
        ).fetchone()
        if not resp:
            raise HTTPException(404, "Response not found.")
        answers = db.execute(
            "SELECT question_id, answer_value FROM survey_answers WHERE response_id=?",
            (response_id,),
        ).fetchall()
    return {
        "id": resp["id"],
        "submitted_at": resp["submitted_at"],
        "is_pilot": bool(resp["is_pilot"]),
        "answers": [{"question_id": a["question_id"], "answer_value": a["answer_value"]} for a in answers],
    }


@router.delete("/surveys/{survey_id}/responses/{response_id}", status_code=204)
def delete_response(survey_id: int, response_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        _own_survey(db, survey_id, user["user_id"])
        resp = db.execute(
            "SELECT id FROM survey_responses WHERE id=? AND survey_id=?",
            (response_id, survey_id),
        ).fetchone()
        if not resp:
            raise HTTPException(404, "Response not found.")
        db.execute("DELETE FROM survey_responses WHERE id=?", (response_id,))


@router.delete("/surveys/{survey_id}/responses", status_code=204)
def delete_responses_bulk(survey_id: int, type: str, user=Depends(get_current_user)):
    if type not in ("pilot", "actual"):
        raise HTTPException(400, "type must be pilot|actual for bulk delete.")
    with get_db() as db:
        _own_survey(db, survey_id, user["user_id"])
        is_pilot = 1 if type == "pilot" else 0
        db.execute("DELETE FROM survey_responses WHERE survey_id=? AND is_pilot=?", (survey_id, is_pilot))


@router.get("/surveys/{survey_id}/export/csv")
def export_responses_csv(survey_id: int, type: str = "all", user=Depends(get_current_user)):
    if type not in ("pilot", "actual", "all"):
        raise HTTPException(400, "type must be pilot|actual|all.")
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        # ordered questions with a display header
        questions = db.execute(
            """SELECT q.id, q.question_text FROM survey_questions q
               JOIN survey_sections sec ON sec.id = q.section_id
               WHERE sec.survey_id = ?
               ORDER BY sec.position, q.position""",
            (survey_id,),
        ).fetchall()
        responses = db.execute(
            "SELECT id, submitted_at, is_pilot FROM survey_responses WHERE survey_id=?" + _type_filter(type)
            + " ORDER BY submitted_at",
            (survey_id,),
        ).fetchall()
        # answer lookup: {response_id: {question_id: value}}
        ans_rows = db.execute(
            """SELECT a.response_id, a.question_id, a.answer_value
               FROM survey_answers a
               JOIN survey_responses r ON r.id = a.response_id
               WHERE r.survey_id = ?""" + (_type_filter(type).replace("is_pilot", "r.is_pilot")),
            (survey_id,),
        ).fetchall()

    answer_map = {}
    for a in ans_rows:
        answer_map.setdefault(a["response_id"], {})[a["question_id"]] = a["answer_value"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    q_ids = [q["id"] for q in questions]
    header = ["response_id", "submitted_at", "is_pilot"] + [
        f"{i + 1}. {(q['question_text'] or '')[:50]}" for i, q in enumerate(questions)
    ]
    writer.writerow(header)
    for r in responses:
        amap = answer_map.get(r["id"], {})
        row = [r["id"], r["submitted_at"], r["is_pilot"]] + [amap.get(qid, "") for qid in q_ids]
        writer.writerow(row)

    safe_name = "".join(ch for ch in (survey["title"] or "survey") if ch.isalnum() or ch in " -_").strip() or "survey"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}-{type}.csv"'},
    )
