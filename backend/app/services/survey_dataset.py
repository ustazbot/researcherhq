"""
Dataset builder for survey analysis (36C-1).

Pivots survey_answers into a pandas DataFrame: one row per response, one column
per question_id. Reverse-coding is applied HERE and only here, so every analysis
downstream consumes an already-reversed frame.

Value typing:
- likert       -> numeric int (reverse-coded if the question is is_reversed=1)
- mcq / demographic -> kept as the label string (descriptive frequency needs labels;
                       no 36C-1 analysis treats these numerically)
- open         -> string (excluded from all numeric statistics)

Missing answers become NaN (pandas), so listwise deletion is a dropna() away.
"""
from typing import Dict

import pandas as pd
from fastapi import HTTPException


def get_question_meta(db, survey_id: int) -> Dict[int, dict]:
    """question_id -> {type, likert_points, is_reversed, options, order}."""
    rows = db.execute(
        """SELECT q.id, q.question_type, q.likert_points, q.is_reversed, q.options_json,
                  sec.position AS sec_pos, q.position AS q_pos
           FROM survey_questions q
           JOIN survey_sections sec ON sec.id = q.section_id
           WHERE sec.survey_id = ?
           ORDER BY sec.position, q.position""",
        (survey_id,),
    ).fetchall()
    import json
    meta = {}
    for r in rows:
        meta[r["id"]] = {
            "type": r["question_type"],
            "likert_points": r["likert_points"],
            "is_reversed": bool(r["is_reversed"]),
            "options": json.loads(r["options_json"]) if r["options_json"] else None,
            "order": (r["sec_pos"], r["q_pos"]),
        }
    return meta


def build_dataframe(db, survey_id: int, source: str) -> pd.DataFrame:
    """Build the response matrix for one data source ('pilot' | 'actual').

    Raises 422 if the source has fewer than 2 responses (nothing to analyse).
    """
    if source not in ("pilot", "actual"):
        raise HTTPException(422, "data_source must be 'pilot' or 'actual'.")
    is_pilot = 1 if source == "pilot" else 0

    responses = db.execute(
        "SELECT id FROM survey_responses WHERE survey_id=? AND is_pilot=? ORDER BY id",
        (survey_id, is_pilot),
    ).fetchall()
    if len(responses) < 2:
        raise HTTPException(422, "Need at least 2 responses to run an analysis.")

    meta = get_question_meta(db, survey_id)
    response_ids = [r["id"] for r in responses]

    answers = db.execute(
        f"""SELECT a.response_id, a.question_id, a.answer_value
            FROM survey_answers a
            WHERE a.response_id IN ({','.join('?' * len(response_ids))})""",
        response_ids,
    ).fetchall()

    # cell[response_id][question_id] = typed value
    cell: Dict[int, Dict[int, object]] = {rid: {} for rid in response_ids}
    for a in answers:
        qid = a["question_id"]
        qm = meta.get(qid)
        if not qm:
            continue
        raw = a["answer_value"]
        if qm["type"] == "likert":
            try:
                val = int(raw)
            except (TypeError, ValueError):
                val = None
            if val is not None and qm["is_reversed"] and qm["likert_points"]:
                val = (qm["likert_points"] + 1) - val
            cell[a["response_id"]][qid] = val
        elif qm["type"] in ("mcq", "demographic"):
            cell[a["response_id"]][qid] = raw
        # open-ended intentionally excluded from the numeric frame

    columns = [qid for qid in meta.keys()
               if meta[qid]["type"] in ("likert", "mcq", "demographic")]
    df = pd.DataFrame.from_dict(cell, orient="index", columns=columns)
    # likert columns to numeric (NaN for missing); label columns stay object
    for qid in columns:
        if meta[qid]["type"] == "likert":
            df[qid] = pd.to_numeric(df[qid], errors="coerce")
    return df
