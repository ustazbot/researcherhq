"""
Public (no-auth) survey response collection — 36B Fasa B.

This is the FIRST public no-auth surface besides auth/webhook, so every
submit passes through 7 security layers (see submit_response). Privacy by
design: we never store raw IP, user-agent, or any respondent identifier —
only a salted SHA256 ip_hash for dedup + rate limiting.
"""
import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.database import get_db
from app.config import settings
from app.services.turnstile_service import verify_turnstile_token
from app.services.rate_limiter import enforce_rate_limit, get_client_ip

router = APIRouter()

MAX_PAYLOAD_BYTES = 100 * 1024
MAX_OPEN_CHARS = 2000
COLLECTING_STATUSES = ("pilot", "published")


class Answer(BaseModel):
    question_id: int
    answer_value: str


class SubmitBody(BaseModel):
    answers: list[Answer]
    turnstile_token: str
    # NOTE: is_pilot is intentionally NOT a field — determined server-side.


def _ip_hash(ip: str) -> str:
    return hashlib.sha256(f"{ip}{settings.app_salt}".encode()).hexdigest()


def _public_structure(db, survey_row) -> dict:
    """Structure for public rendering. Exposes ONLY what the form needs —
    no user_id, project_id, survey numeric id, email, or timestamps."""
    sections = db.execute(
        "SELECT id, title, position FROM survey_sections WHERE survey_id=? ORDER BY position",
        (survey_row["id"],),
    ).fetchall()
    out = []
    for sec in sections:
        qs = db.execute(
            "SELECT id, question_text, question_type, options_json, likert_points, position "
            "FROM survey_questions WHERE section_id=? ORDER BY position",
            (sec["id"],),
        ).fetchall()
        out.append({
            "title": sec["title"],
            "questions": [
                {
                    "id": q["id"],
                    "question_text": q["question_text"],
                    "question_type": q["question_type"],
                    "options": json.loads(q["options_json"]) if q["options_json"] else None,
                    "likert_points": q["likert_points"],
                }
                for q in qs
            ],
        })
    return {"title": survey_row["title"], "sections": out}


@router.get("/surveys/{share_token}")
def get_public_survey(share_token: str):
    with get_db() as db:
        survey = db.execute(
            "SELECT id, title, status FROM surveys WHERE share_token=?",
            (share_token,),
        ).fetchone()
        if not survey:
            raise HTTPException(404, "Survey not found.")
        if survey["status"] not in COLLECTING_STATUSES:
            raise HTTPException(410, "This survey is not accepting responses.")
        return _public_structure(db, survey)


@router.post("/surveys/{share_token}/responses", status_code=201)
async def submit_response(share_token: str, body: SubmitBody, request: Request):
    ip = get_client_ip(request)
    ip_hash = _ip_hash(ip)

    # Layer 5a — payload size cap (read cached body; Starlette caches it)
    raw = await request.body()
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise HTTPException(413, "Payload too large.")

    # Layer 1 — Turnstile (fails closed)
    if not await verify_turnstile_token(body.turnstile_token, remoteip=ip):
        raise HTTPException(403, "Verification failed. Please try again.")

    # Layer 2 — app-level rate limiting (defense behind nginx limit_req)
    enforce_rate_limit(f"survey_submit:{ip_hash}", max_attempts=5, window_minutes=10)

    with get_db() as db:
        survey = db.execute(
            "SELECT id, status, mode, response_cap FROM surveys WHERE share_token=?",
            (share_token,),
        ).fetchone()
        if not survey:
            raise HTTPException(404, "Survey not found.")

        # Per-survey throttle (layer 2, cont.)
        enforce_rate_limit(f"survey_submit_survey:{survey['id']}", max_attempts=30, window_minutes=1)

        # Layer 4 — status
        if survey["status"] not in COLLECTING_STATUSES:
            raise HTTPException(410, "This survey is not accepting responses.")

        # Layer 3 — response cap for the current mode
        current = db.execute(
            "SELECT COUNT(*) AS c FROM survey_responses WHERE survey_id=?",
            (survey["id"],),
        ).fetchone()["c"]
        if current >= survey["response_cap"]:
            raise HTTPException(409, "This survey has reached its response limit.")

        # Layer 5b — payload validation against the real structure
        q_rows = db.execute(
            """SELECT q.id, q.question_type, q.options_json, q.likert_points
               FROM survey_questions q
               JOIN survey_sections sec ON sec.id = q.section_id
               WHERE sec.survey_id = ?""",
            (survey["id"],),
        ).fetchall()
        questions = {q["id"]: q for q in q_rows}
        submitted = {a.question_id: a.answer_value for a in body.answers}

        # every question must belong to this survey; no stray ids
        for qid in submitted:
            if qid not in questions:
                raise HTTPException(422, "Invalid question in submission.")
        # all questions required
        if set(submitted.keys()) != set(questions.keys()):
            raise HTTPException(422, "All questions must be answered.")

        for qid, q in questions.items():
            val = submitted[qid]
            if val is None or str(val).strip() == "":
                raise HTTPException(422, "All questions must be answered.")
            qtype = q["question_type"]
            options = json.loads(q["options_json"]) if q["options_json"] else []
            if qtype == "likert":
                points = q["likert_points"] or (len(options) if options else 5)
                try:
                    iv = int(val)
                except (TypeError, ValueError):
                    raise HTTPException(422, "Invalid Likert value.")
                if iv < 1 or iv > points:
                    raise HTTPException(422, "Likert value out of range.")
            elif qtype in ("mcq", "demographic"):
                if options and val not in options:
                    raise HTTPException(422, "Invalid option selected.")
            elif qtype == "open":
                if len(val) > MAX_OPEN_CHARS:
                    raise HTTPException(422, "Answer too long.")

        # Layer 6 — dedup: same ip_hash + survey within ~60s
        enforce_rate_limit(f"survey_dedup:{survey['id']}:{ip_hash}", max_attempts=1, window_minutes=1)

        # is_pilot decided SERVER-SIDE from current mode
        is_pilot = 1 if survey["status"] == "pilot" else 0

        # Layer 7 — atomic insert (get_db commits once / rolls back on error)
        now = datetime.utcnow().isoformat()
        cur = db.execute(
            "INSERT INTO survey_responses (survey_id, is_pilot, submitted_at, ip_hash) VALUES (?,?,?,?)",
            (survey["id"], is_pilot, now, ip_hash),
        )
        response_id = cur.lastrowid
        for qid, q in questions.items():
            db.execute(
                "INSERT INTO survey_answers (response_id, question_id, answer_value) VALUES (?,?,?)",
                (response_id, qid, submitted[qid]),
            )

    return {"status": "ok"}
