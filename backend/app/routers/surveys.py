import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.database import get_db
from app.routers.auth import get_current_user
from app.routers.rag import deduct_credits
from app.services.export_service import build_survey_docx
from app.services.survey_generator import generate_survey_content

router = APIRouter()

GENERATE_COST_FULL = 10
GENERATE_COST_SECTION = 3


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
        raise HTTPException(404, "Projek tidak dijumpai.")
    return row


def _own_survey(db, survey_id, user_id):
    row = db.execute(
        """SELECT s.*, p.output_language FROM surveys s
           JOIN projects p ON p.id = s.project_id
           WHERE s.id=? AND p.user_id=?""",
        (survey_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Soal selidik tidak dijumpai.")
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
        raise HTTPException(404, "Bahagian tidak dijumpai.")
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
        raise HTTPException(404, "Soalan tidak dijumpai.")
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
    return {
        "id": survey_row["id"],
        "project_id": survey_row["project_id"],
        "title": survey_row["title"],
        "status": survey_row["status"],
        "created_at": survey_row["created_at"],
        "updated_at": survey_row["updated_at"],
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
        now = datetime.utcnow().isoformat()
        cur = db.execute(
            "INSERT INTO surveys (project_id, title, status, created_at, updated_at) VALUES (?,?,'draft',?,?)",
            (project_id, body.title or "Soal Selidik", now, now),
        )
        sid = cur.lastrowid
    return {"id": sid, "project_id": project_id, "title": body.title or "Soal Selidik", "status": "draft"}


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


# ── AI Generation ────────────────────────────────────────────────

@router.post("/surveys/{survey_id}/generate")
async def generate_survey(survey_id: int, body: GenerateBody, user=Depends(get_current_user)):
    if body.scope not in ("full", "section"):
        raise HTTPException(400, "Scope tidak sah. Guna 'full' atau 'section'.")
    cost = GENERATE_COST_FULL if body.scope == "full" else GENERATE_COST_SECTION

    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        project_id = survey["project_id"]
        output_language = survey["output_language"] or "bm"

        doc_count = db.execute(
            "SELECT COUNT(*) AS c FROM documents WHERE project_id=?", (project_id,)
        ).fetchone()["c"]
        if doc_count == 0:
            raise HTTPException(
                400,
                "Tiada dokumen dalam projek ini. Muat naik kertas kerja atau proposal anda dahulu — instrumen dijana berdasarkan dokumen projek.",
            )

        kredit = db.execute(
            "SELECT kredit_remaining FROM users WHERE id=?", (user["user_id"],)
        ).fetchone()
        if not kredit or kredit["kredit_remaining"] < cost:
            raise HTTPException(402, "Kredit Kajian tidak mencukupi.")

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
        raise HTTPException(502, f"Penjanaan gagal: {e}. Kredit tidak ditolak — cuba semula.")

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

        # kredit ditolak HANYA selepas generation berjaya
        new_kredit = deduct_credits(db, user["user_id"], cost)
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
        db.execute("DELETE FROM survey_sections WHERE id=?", (section_id,))
        _touch_survey(db, sec["survey_id"])


# ── Question CRUD ────────────────────────────────────────────────

@router.post("/sections/{section_id}/questions", status_code=201)
def create_question(section_id: int, body: QuestionCreate, user=Depends(get_current_user)):
    if body.question_type not in ("likert", "mcq", "open", "demographic"):
        raise HTTPException(400, "Jenis soalan tidak sah.")
    with get_db() as db:
        sec = _own_section(db, section_id, user["user_id"])
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
        raise HTTPException(400, "Jenis soalan tidak sah.")
    with get_db() as db:
        q = _own_question(db, question_id, user["user_id"])
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
        db.execute("DELETE FROM survey_questions WHERE id=?", (question_id,))
        sec = _own_section(db, q["section_id"], user["user_id"])
        _touch_survey(db, sec["survey_id"])


# ── Export ───────────────────────────────────────────────────────

@router.get("/surveys/{survey_id}/export/docx")
def export_survey_docx(survey_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        survey = _own_survey(db, survey_id, user["user_id"])
        full = _survey_full(db, survey)

    docx_bytes = build_survey_docx(full["title"], full["sections"])
    safe_name = "".join(ch for ch in full["title"] if ch.isalnum() or ch in " -_").strip() or "soal-selidik"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.docx"'},
    )
