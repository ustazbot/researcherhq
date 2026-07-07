"""
External data import (36C-4): CSV/XLSX -> survey with status='imported'.

Two-step flow: preview parses the file in-memory (nothing written to the DB)
and caches the parsed frame under a short-lived token; confirm turns the
cached frame + user column mappings into a normal survey structure that the
existing analysis engine (survey_dataset/survey_stats/interpretation_guard)
consumes unchanged.

PII protection is a column-NAME heuristic only — the UI tells the user to
verify the content themselves. Suspected columns must be skipped or
explicitly overridden.
"""
import hashlib
import io
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from fastapi import HTTPException

from app.config import settings

MAX_FILE_BYTES = 5 * 1024 * 1024   # 5MB
MAX_ROWS = 1000                    # aligned with the 36B 'actual' cap
MAX_COLS = 60
MAX_MCQ_OPTIONS = 12
PREVIEW_TTL_MINUTES = 10
LIKERT_POINTS_ALLOWED = (4, 5, 7)
QUESTION_TYPES = ("likert", "mcq", "open", "demographic")

PII_HEADER_PATTERNS = [
    r"e[- ]?mel|email", r"nama|name", r"no\.?\s*k/?p|ic\s*no|kad\s*pengenalan",
    r"telefon|phone|no\.?\s*hp|mobile", r"alamat|address",
]
_PII_RE = re.compile("|".join(PII_HEADER_PATTERNS), re.IGNORECASE)

# preview_token -> {expires, filename, df}. In-memory (single-process API);
# a lost token just means re-uploading the file.
_PREVIEW_CACHE: Dict[str, dict] = {}


def pii_suspected(column_name: str) -> bool:
    """Pure heuristic on the column NAME only (content is never scanned)."""
    return bool(_PII_RE.search(str(column_name)))


def parse_upload(filename: str, data: bytes) -> pd.DataFrame:
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(413, f"File is {len(data) / (1024 * 1024):.1f}MB — the limit is 5MB.")
    name = (filename or "").lower()
    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(data))
        elif name.endswith(".xlsx"):
            df = pd.read_excel(io.BytesIO(data), engine="openpyxl")
        else:
            raise HTTPException(422, "Unsupported file type — upload a .csv or .xlsx file.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Could not parse the file. Check that it is a valid CSV or XLSX.")
    if df.shape[0] == 0:
        raise HTTPException(422, "The file contains no data rows.")
    if df.shape[0] > MAX_ROWS:
        raise HTTPException(422, f"The file has {df.shape[0]} data rows — the limit is {MAX_ROWS}.")
    if df.shape[1] > MAX_COLS:
        raise HTTPException(422, f"The file has {df.shape[1]} columns — the limit is {MAX_COLS}.")
    df.columns = [str(c) for c in df.columns]
    return df


def _purge_expired():
    now = datetime.utcnow()
    for tok in [t for t, v in _PREVIEW_CACHE.items() if v["expires"] < now]:
        del _PREVIEW_CACHE[tok]


def cache_preview(filename: str, df: pd.DataFrame) -> str:
    _purge_expired()
    token = secrets.token_urlsafe(24)
    _PREVIEW_CACHE[token] = {
        "expires": datetime.utcnow() + timedelta(minutes=PREVIEW_TTL_MINUTES),
        "filename": filename,
        "df": df,
    }
    return token


def get_preview(token: str) -> Tuple[str, pd.DataFrame]:
    """Non-destructive read — a mapping validation error must not force a
    re-upload. Call drop_preview() only after a successful import."""
    _purge_expired()
    entry = _PREVIEW_CACHE.get(token)
    if not entry:
        raise HTTPException(410, "The upload preview has expired — please upload the file again.")
    return entry["filename"], entry["df"]


def drop_preview(token: str):
    _PREVIEW_CACHE.pop(token, None)


def build_preview_response(token: str, filename: str, df: pd.DataFrame) -> dict:
    sample = df.head(5)
    return {
        "preview_token": token,
        "filename": filename,
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "columns": [{"name": c, "pii_suspected": pii_suspected(c)} for c in df.columns],
        "sample_rows": [
            ["" if pd.isna(v) else str(v) for v in row]
            for row in sample.itertuples(index=False, name=None)
        ],
        "pii_note": "This checks column names only — please also verify the content yourself before importing.",
    }


# ── Mapping validation + survey build ────────────────────────────

def validate_mappings(df: pd.DataFrame, mappings: List[dict]) -> List[dict]:
    """Returns the ordered list of question-mapped columns (validated)."""
    by_name = {m.get("column_name"): m for m in mappings}
    for name in by_name:
        if name not in df.columns:
            raise HTTPException(422, f"Column '{name}' does not exist in the uploaded file.")
    questions = []
    for col in df.columns:  # position follows file column order
        m = by_name.get(col)
        if not m or m.get("action") == "skip":
            continue
        if m.get("action") != "question":
            raise HTTPException(422, f"Column '{col}': action must be 'skip' or 'question'.")
        if pii_suspected(col) and not m.get("override_pii_warning"):
            raise HTTPException(422, f"Column '{col}' looks like it may contain personal data. "
                                     "Exclude it or confirm override.")
        qtype = m.get("question_type")
        if qtype not in QUESTION_TYPES:
            raise HTTPException(422, f"Column '{col}': question_type must be one of {', '.join(QUESTION_TYPES)}.")
        entry = {"column": col, "type": qtype,
                 "is_reversed": 1 if m.get("is_reversed") else 0, "likert_points": None, "options": None}
        if qtype == "likert":
            points = m.get("likert_points")
            if points not in LIKERT_POINTS_ALLOWED:
                raise HTTPException(422, f"Column '{col}': a Likert column needs likert_points of 4, 5 or 7.")
            entry["likert_points"] = points
        elif qtype in ("mcq", "demographic"):
            uniques = sorted({str(v).strip() for v in df[col].dropna() if str(v).strip() != ""})
            if len(uniques) > MAX_MCQ_OPTIONS:
                raise HTTPException(422, f"Too many distinct values ({len(uniques)}) for a multiple-choice "
                                         f"column '{col}' — consider marking it 'open text'.")
            if not uniques:
                raise HTTPException(422, f"Column '{col}' has no values to derive options from.")
            entry["options"] = uniques
        questions.append(entry)
    if not questions:
        raise HTTPException(422, "Map at least one column as a question.")
    return questions


def _cell_value(qtype: str, likert_points: Optional[int], raw) -> Optional[str]:
    """Normalise one cell to the stored answer_value, or None for missing."""
    if pd.isna(raw):
        return None
    if qtype == "likert":
        try:
            val = int(float(raw))
        except (TypeError, ValueError):
            return None
        if not (1 <= val <= likert_points):
            return None  # out of scale -> missing, never a rejected import
        return str(val)
    s = str(raw).strip()
    return s if s else None


def create_imported_survey(db, project_id: str, title: str, is_pilot: bool,
                           filename: str, df: pd.DataFrame, questions: List[dict]) -> dict:
    """One transaction (caller's get_db context): survey + section + questions
    + responses + answers. Rows with no mapped values at all are skipped."""
    now = datetime.utcnow().isoformat()
    sid = db.execute(
        """INSERT INTO surveys (project_id, title, status, import_filename, imported_at,
                                imported_row_count, created_at, updated_at)
           VALUES (?,?,'imported',?,?,?,?,?)""",
        (project_id, title, filename, now, int(df.shape[0]), now, now),
    ).lastrowid
    secid = db.execute(
        "INSERT INTO survey_sections (survey_id, title, position) VALUES (?, 'Imported Data', 0)",
        (sid,),
    ).lastrowid
    qids = {}
    for pos, q in enumerate(questions):
        qids[q["column"]] = db.execute(
            """INSERT INTO survey_questions (section_id, question_text, question_type, options_json,
               likert_points, is_reversed, position) VALUES (?,?,?,?,?,?,?)""",
            (secid, q["column"], q["type"],
             json.dumps(q["options"], ensure_ascii=False) if q["options"] else None,
             q["likert_points"], q["is_reversed"], pos),
        ).lastrowid

    imported, skipped = 0, 0
    pilot_flag = 1 if is_pilot else 0
    for row_index, (_, row) in enumerate(df.iterrows()):
        values = []
        for q in questions:
            v = _cell_value(q["type"], q["likert_points"], row[q["column"]])
            values.append((q["column"], v))
        if all(v is None for _, v in values):
            skipped += 1
            continue
        # synthetic per-row hash — NOT a real IP; unique per row to avoid collisions
        ip_hash = hashlib.sha256(f"import:{sid}:{row_index}:{settings.app_salt}".encode()).hexdigest()
        rid = db.execute(
            "INSERT INTO survey_responses (survey_id, is_pilot, submitted_at, ip_hash) VALUES (?,?,?,?)",
            (sid, pilot_flag, now, ip_hash),
        ).lastrowid
        for col, v in values:
            if v is None:
                continue  # missing stays absent, same as native collection
            db.execute("INSERT INTO survey_answers (response_id, question_id, answer_value) VALUES (?,?,?)",
                       (rid, qids[col], v))
        imported += 1
    return {"survey_id": sid, "question_count": len(questions),
            "imported_responses": imported, "skipped_rows": skipped}
