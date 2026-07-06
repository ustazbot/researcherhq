"""
Survey analysis endpoints (36C-1). Pure stats, zero AI, zero credit cost.

Constructs are an analysis layer, not survey structure, so they can be edited
even while the survey is collecting responses. Deleting a question cascades its
construct_items away, but saved analyses keep their result_json snapshot.
"""
import json
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.database import get_db
from app.routers.auth import get_current_user
from app.services.survey_dataset import build_dataframe, get_question_meta
from app.services import survey_stats
from app.services.export_service import build_apa_docx

router = APIRouter()

ANALYSIS_TYPES = ("descriptive", "reliability", "normality")


# ── bodies ───────────────────────────────────────────────────────

class ConstructCreate(BaseModel):
    name: str
    question_ids: List[int]
    position: Optional[int] = None


class ConstructUpdate(BaseModel):
    name: Optional[str] = None
    question_ids: Optional[List[int]] = None


class AnalysisRun(BaseModel):
    analysis_type: str
    data_source: str  # 'pilot' | 'actual'
    construct_ids: Optional[List[int]] = None
    question_ids: Optional[List[int]] = None


# ── ownership + Pro gating ───────────────────────────────────────

def _own_survey_pro(db, survey_id, user_id):
    row = db.execute(
        """SELECT s.*, u.tier FROM surveys s
           JOIN projects p ON p.id = s.project_id
           JOIN users u ON u.id = p.user_id
           WHERE s.id=? AND p.user_id=?""",
        (survey_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Survey not found.")
    if row["tier"] != "pro":
        raise HTTPException(403, "The Survey module is available on the Pro plan only.")
    return row


def _own_construct(db, construct_id, user_id):
    row = db.execute(
        """SELECT c.* FROM survey_constructs c
           JOIN surveys s ON s.id = c.survey_id
           JOIN projects p ON p.id = s.project_id
           WHERE c.id=? AND p.user_id=?""",
        (construct_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Construct not found.")
    return row


def _validate_likert_items(db, survey_id, question_ids):
    """All items must be likert questions of this survey, sharing likert_points."""
    if not question_ids:
        raise HTTPException(422, "A construct needs at least one question.")
    rows = db.execute(
        f"""SELECT q.id, q.question_type, q.likert_points
            FROM survey_questions q
            JOIN survey_sections sec ON sec.id = q.section_id
            WHERE sec.survey_id = ? AND q.id IN ({','.join('?' * len(question_ids))})""",
        [survey_id, *question_ids],
    ).fetchall()
    found = {r["id"]: r for r in rows}
    for qid in question_ids:
        if qid not in found:
            raise HTTPException(422, "A question does not belong to this survey.")
        if found[qid]["question_type"] != "likert":
            raise HTTPException(422, "Only Likert questions can be added to a construct.")
    points = {found[qid]["likert_points"] for qid in question_ids}
    if len(points) > 1:
        raise HTTPException(422, "All items in a construct must share the same Likert scale.")


def _construct_with_items(db, construct_row) -> dict:
    items = db.execute(
        "SELECT question_id FROM survey_construct_items WHERE construct_id=? ORDER BY id",
        (construct_row["id"],),
    ).fetchall()
    return {
        "id": construct_row["id"],
        "survey_id": construct_row["survey_id"],
        "name": construct_row["name"],
        "position": construct_row["position"],
        "question_ids": [r["question_id"] for r in items],
    }


# ── Constructs CRUD ──────────────────────────────────────────────

@router.post("/surveys/{survey_id}/constructs", status_code=201)
def create_construct(survey_id: int, body: ConstructCreate, user=Depends(get_current_user)):
    with get_db() as db:
        _own_survey_pro(db, survey_id, user["user_id"])
        _validate_likert_items(db, survey_id, body.question_ids)
        if body.position is None:
            mx = db.execute("SELECT COALESCE(MAX(position),-1) AS m FROM survey_constructs WHERE survey_id=?",
                            (survey_id,)).fetchone()["m"]
            position = mx + 1
        else:
            position = body.position
        cur = db.execute(
            "INSERT INTO survey_constructs (survey_id, name, position) VALUES (?,?,?)",
            (survey_id, body.name, position),
        )
        cid = cur.lastrowid
        for qid in body.question_ids:
            db.execute("INSERT INTO survey_construct_items (construct_id, question_id) VALUES (?,?)", (cid, qid))
        row = db.execute("SELECT * FROM survey_constructs WHERE id=?", (cid,)).fetchone()
        return _construct_with_items(db, row)


@router.get("/surveys/{survey_id}/constructs")
def list_constructs(survey_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        _own_survey_pro(db, survey_id, user["user_id"])
        rows = db.execute("SELECT * FROM survey_constructs WHERE survey_id=? ORDER BY position", (survey_id,)).fetchall()
        return [_construct_with_items(db, r) for r in rows]


@router.patch("/constructs/{construct_id}")
def update_construct(construct_id: int, body: ConstructUpdate, user=Depends(get_current_user)):
    with get_db() as db:
        c = _own_construct(db, construct_id, user["user_id"])
        if body.name is not None:
            db.execute("UPDATE survey_constructs SET name=? WHERE id=?", (body.name, construct_id))
        if body.question_ids is not None:
            _validate_likert_items(db, c["survey_id"], body.question_ids)
            db.execute("DELETE FROM survey_construct_items WHERE construct_id=?", (construct_id,))
            for qid in body.question_ids:
                db.execute("INSERT INTO survey_construct_items (construct_id, question_id) VALUES (?,?)",
                           (construct_id, qid))
        row = db.execute("SELECT * FROM survey_constructs WHERE id=?", (construct_id,)).fetchone()
        return _construct_with_items(db, row)


@router.delete("/constructs/{construct_id}", status_code=204)
def delete_construct(construct_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        _own_construct(db, construct_id, user["user_id"])
        db.execute("DELETE FROM survey_constructs WHERE id=?", (construct_id,))


# ── Run analysis ─────────────────────────────────────────────────

def _resolve_constructs(db, construct_ids):
    out = []
    for cid in (construct_ids or []):
        row = db.execute("SELECT * FROM survey_constructs WHERE id=?", (cid,)).fetchone()
        if not row:
            raise HTTPException(404, "Construct not found.")
        items = [r["question_id"] for r in db.execute(
            "SELECT question_id FROM survey_construct_items WHERE construct_id=? ORDER BY id", (cid,)).fetchall()]
        out.append({"id": cid, "name": row["name"], "items": items})
    return out


@router.post("/surveys/{survey_id}/analyses")
def run_analysis(survey_id: int, body: AnalysisRun, user=Depends(get_current_user)):
    if body.analysis_type not in ANALYSIS_TYPES:
        raise HTTPException(400, "analysis_type must be descriptive|reliability|normality.")
    with get_db() as db:
        _own_survey_pro(db, survey_id, user["user_id"])
        df = build_dataframe(db, survey_id, body.data_source)
        meta = get_question_meta(db, survey_id)
        constructs = _resolve_constructs(db, body.construct_ids)

        results, apa_tables = [], []

        if body.analysis_type == "descriptive":
            qids = body.question_ids or [q for q in meta if meta[q]["type"] != "open"]
            res = survey_stats.run_descriptive(df, meta, qids, constructs)
            results.append(res)
            apa_tables.append(res["apa_table"])

        elif body.analysis_type == "reliability":
            if not constructs:
                raise HTTPException(422, "Reliability analysis requires at least one construct.")
            for c in constructs:
                res = survey_stats.run_reliability(df, c["items"], c["name"])
                results.append(res)
                apa_tables.append(res["apa_table"])

        else:  # normality
            targets = 0
            for c in constructs:
                res = survey_stats.run_normality(df, meta, construct=c)
                results.append(res); apa_tables.append(res["apa_table"]); targets += 1
            for qid in (body.question_ids or []):
                if meta.get(qid, {}).get("type") != "likert":
                    raise HTTPException(422, "Normality items must be Likert questions.")
                res = survey_stats.run_normality(df, meta, item_qid=qid)
                results.append(res); apa_tables.append(res["apa_table"]); targets += 1
            if targets == 0:
                raise HTTPException(422, "Normality analysis requires a construct or a Likert item.")

        result_json = {
            "analysis_type": body.analysis_type,
            "data_source": body.data_source,
            "results": results,
            "apa_tables": apa_tables,
        }
        params_json = {
            "construct_ids": body.construct_ids or [],
            "question_ids": body.question_ids or [],
        }
        now = datetime.utcnow().isoformat()
        cur = db.execute(
            """INSERT INTO survey_analyses (survey_id, analysis_type, data_source, params_json, result_json, created_at)
               VALUES (?,?,?,?,?,?)""",
            (survey_id, body.analysis_type, body.data_source,
             json.dumps(params_json), json.dumps(result_json), now),
        )
        aid = cur.lastrowid
    return {"id": aid, "analysis_type": body.analysis_type, "data_source": body.data_source, **result_json}


@router.get("/surveys/{survey_id}/analyses")
def list_analyses(survey_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        _own_survey_pro(db, survey_id, user["user_id"])
        rows = db.execute(
            "SELECT id, analysis_type, data_source, created_at FROM survey_analyses WHERE survey_id=? ORDER BY created_at DESC",
            (survey_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            """SELECT a.* FROM survey_analyses a
               JOIN surveys s ON s.id = a.survey_id
               JOIN projects p ON p.id = s.project_id
               WHERE a.id=? AND p.user_id=?""",
            (analysis_id, user["user_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Analysis not found.")
        # returned straight from result_json — never recomputed
        return {
            "id": row["id"],
            "analysis_type": row["analysis_type"],
            "data_source": row["data_source"],
            "created_at": row["created_at"],
            **json.loads(row["result_json"]),
        }


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            """SELECT a.id FROM survey_analyses a
               JOIN surveys s ON s.id = a.survey_id
               JOIN projects p ON p.id = s.project_id
               WHERE a.id=? AND p.user_id=?""",
            (analysis_id, user["user_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Analysis not found.")
        db.execute("DELETE FROM survey_analyses WHERE id=?", (analysis_id,))


@router.get("/analyses/{analysis_id}/export/docx")
def export_analysis_docx(analysis_id: int, user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            """SELECT a.*, s.title FROM survey_analyses a
               JOIN surveys s ON s.id = a.survey_id
               JOIN projects p ON p.id = s.project_id
               WHERE a.id=? AND p.user_id=?""",
            (analysis_id, user["user_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Analysis not found.")
        result = json.loads(row["result_json"])
        title = f"{row['title']} — {row['analysis_type'].title()} ({row['data_source']})"

    docx_bytes = build_apa_docx(title, result.get("apa_tables", []))
    safe = "".join(ch for ch in (row["title"] or "analysis") if ch.isalnum() or ch in " -_").strip() or "analysis"
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{safe}-{row["analysis_type"]}.docx"'},
    )
