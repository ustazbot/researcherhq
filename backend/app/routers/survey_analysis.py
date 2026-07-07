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
from app.routers.rag import deduct_credits
from app.services.survey_dataset import build_dataframe, get_question_meta
from app.services import survey_stats, interpretation_guard
from app.services.export_service import build_apa_docx

router = APIRouter()

ANALYSIS_TYPES = (
    "descriptive", "reliability", "normality",
    # 36C-2 inferential
    "ttest_independent", "ttest_paired", "anova_oneway",
    "mann_whitney", "kruskal_wallis", "wilcoxon",
    "correlation", "chi_square",
)
GROUP_TESTS = ("ttest_independent", "anova_oneway", "mann_whitney", "kruskal_wallis")
PAIRED_TESTS = ("ttest_paired", "wilcoxon")


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
    # 36C-2 inferential params
    outcome: Optional[dict] = None            # {"construct_id": X} | {"question_id": Y}
    outcome2: Optional[dict] = None           # second variable for paired tests
    grouping_question_id: Optional[int] = None
    variables: Optional[List[dict]] = None    # correlation: list of outcome specs


class WizardBody(BaseModel):
    goal: str  # 'compare_groups' | 'relationship' | 'association_categorical'
    outcome: dict
    grouping_question_id: Optional[int] = None
    paired: bool = False
    data_source: str = "actual"


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


def _resolve_outcome(db, survey_id, df, meta, spec):
    """Resolve an outcome spec into (label, numeric pandas Series).

    {"construct_id": X} -> composite mean of the construct's items (listwise rows)
    {"question_id": Y}  -> the Likert item column
    """
    if not spec or not isinstance(spec, dict):
        raise HTTPException(422, "Outcome must specify a construct_id or a question_id.")
    if spec.get("construct_id") is not None:
        cid = spec["construct_id"]
        row = db.execute("SELECT * FROM survey_constructs WHERE id=? AND survey_id=?",
                         (cid, survey_id)).fetchone()
        if not row:
            raise HTTPException(404, "Construct not found.")
        items = [r["question_id"] for r in db.execute(
            "SELECT question_id FROM survey_construct_items WHERE construct_id=? ORDER BY id", (cid,)).fetchall()]
        if not items:
            raise HTTPException(422, "Construct has no items.")
        sub = df[items].dropna()
        return row["name"], sub.mean(axis=1)
    if spec.get("question_id") is not None:
        qid = spec["question_id"]
        qm = meta.get(qid)
        if not qm:
            raise HTTPException(422, "Outcome question does not belong to this survey.")
        if qm["type"] != "likert":
            raise HTTPException(422, "Outcome must be a construct or a Likert question.")
        import pandas as pd
        return f"Q{qid}", pd.to_numeric(df[qid], errors="coerce")
    raise HTTPException(422, "Outcome must specify a construct_id or a question_id.")


@router.post("/surveys/{survey_id}/analyses")
def run_analysis(survey_id: int, body: AnalysisRun, user=Depends(get_current_user)):
    if body.analysis_type not in ANALYSIS_TYPES:
        raise HTTPException(400, f"analysis_type must be one of: {', '.join(ANALYSIS_TYPES)}.")
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

        elif body.analysis_type == "normality":
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

        elif body.analysis_type in GROUP_TESTS:
            if body.grouping_question_id is None:
                raise HTTPException(422, "This test requires a grouping_question_id.")
            label, series = _resolve_outcome(db, survey_id, df, meta, body.outcome)
            glabel = f"Q{body.grouping_question_id}"
            fn = {
                "ttest_independent": survey_stats.run_ttest_independent,
                "anova_oneway": survey_stats.run_anova_oneway,
                "mann_whitney": survey_stats.run_mann_whitney,
                "kruskal_wallis": survey_stats.run_kruskal_wallis,
            }[body.analysis_type]
            res = fn(df, meta, label, series, body.grouping_question_id, glabel)
            results.append(res)
            apa_tables.append(res["apa_table"])
            if res.get("posthoc_apa_table"):
                apa_tables.append(res["posthoc_apa_table"])

        elif body.analysis_type in PAIRED_TESTS:
            la, sa = _resolve_outcome(db, survey_id, df, meta, body.outcome)
            lb, sb = _resolve_outcome(db, survey_id, df, meta, body.outcome2)
            res = survey_stats.run_paired_test(body.analysis_type, la, sa, lb, sb)
            results.append(res)
            apa_tables.append(res["apa_table"])

        elif body.analysis_type == "correlation":
            specs = body.variables or []
            if len(specs) < 2:
                raise HTTPException(422, "Correlation analysis requires at least 2 variables.")
            variables = [_resolve_outcome(db, survey_id, df, meta, s) for s in specs]
            res = survey_stats.run_correlation(variables)
            results.append(res)
            apa_tables.append(res["apa_table"])
            apa_tables.append(res["spearman_apa_table"])

        else:  # chi_square
            qids = body.question_ids or []
            if len(qids) != 2:
                raise HTTPException(422, "Chi-square requires exactly 2 categorical question_ids.")
            res = survey_stats.run_chi_square(df, meta, qids[0], qids[1])
            results.append(res)
            apa_tables.append(res["apa_table"])

        result_json = {
            "analysis_type": body.analysis_type,
            "data_source": body.data_source,
            "results": results,
            "apa_tables": apa_tables,
        }
        params_json = {
            "construct_ids": body.construct_ids or [],
            "question_ids": body.question_ids or [],
            "outcome": body.outcome,
            "outcome2": body.outcome2,
            "grouping_question_id": body.grouping_question_id,
            "variables": body.variables,
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


# ── Analysis Wizard (36C-2) ──────────────────────────────────────
# Deterministic Python decision tree — no LLM, no credits, nothing saved.

WIZARD_JUSTIFICATIONS = {
    "ttest_independent": ("Two groups with approximately normal distribution → independent samples t-test. "
                          "If normality is a concern, Mann-Whitney U is the non-parametric alternative."),
    "mann_whitney": ("Two groups with non-normal distribution → Mann-Whitney U test. "
                     "The independent samples t-test is the parametric alternative for larger samples."),
    "anova_oneway": ("Three or more groups with approximately normal distribution → one-way ANOVA "
                     "with Tukey HSD post-hoc. Kruskal-Wallis is the non-parametric alternative."),
    "kruskal_wallis": ("Three or more groups with non-normal distribution → Kruskal-Wallis test. "
                       "One-way ANOVA is the parametric alternative for larger samples."),
    "ttest_paired": ("Paired measurements with approximately normal distribution → paired samples t-test. "
                     "Wilcoxon signed-rank is the non-parametric alternative."),
    "wilcoxon": ("Paired measurements with non-normal distribution → Wilcoxon signed-rank test. "
                 "The paired samples t-test is the parametric alternative for larger samples."),
    "correlation": ("Numeric variables → correlation analysis. Pearson and Spearman coefficients are "
                    "both reported; prefer Spearman when distributions are skewed."),
    "chi_square": "Two categorical questions → chi-square test of independence with Cramér's V effect size.",
}
WIZARD_ALTERNATIVES = {
    "ttest_independent": "mann_whitney", "mann_whitney": "ttest_independent",
    "anova_oneway": "kruskal_wallis", "kruskal_wallis": "anova_oneway",
    "ttest_paired": "wilcoxon", "wilcoxon": "ttest_paired",
    "correlation": None, "chi_square": None,
}


@router.post("/surveys/{survey_id}/wizard")
def analysis_wizard(survey_id: int, body: WizardBody, user=Depends(get_current_user)):
    if body.goal not in ("compare_groups", "relationship", "association_categorical"):
        raise HTTPException(422, "goal must be compare_groups|relationship|association_categorical.")
    with get_db() as db:
        _own_survey_pro(db, survey_id, user["user_id"])
        df = build_dataframe(db, survey_id, body.data_source)
        meta = get_question_meta(db, survey_id)

        group_summary, normality_summary = None, None

        if body.goal == "association_categorical":
            qid = (body.outcome or {}).get("question_id")
            if qid is None or meta.get(qid, {}).get("type") not in ("mcq", "demographic"):
                raise HTTPException(422, "Categorical association requires a categorical (MCQ or demographic) outcome question.")
            if body.grouping_question_id is None or \
               meta.get(body.grouping_question_id, {}).get("type") not in ("mcq", "demographic"):
                raise HTTPException(422, "Categorical association requires a categorical grouping_question_id.")
            suggested = "chi_square"

        elif body.goal == "relationship":
            _label, series = _resolve_outcome(db, survey_id, df, meta, body.outcome)
            normality_summary = survey_stats._norm_check(series.dropna().to_numpy())
            suggested = "correlation"

        else:  # compare_groups
            label, series = _resolve_outcome(db, survey_id, df, meta, body.outcome)
            if body.paired:
                normality_summary = survey_stats._norm_check(series.dropna().to_numpy())
                normal = normality_summary.get("looks_normal") is not False
                suggested = "ttest_paired" if normal else "wilcoxon"
            else:
                if body.grouping_question_id is None:
                    raise HTTPException(422, "compare_groups requires a grouping_question_id.")
                kept, excluded, group_summary = survey_stats.build_groups(
                    df, meta, series, body.grouping_question_id)
                normality_summary = {lbl: survey_stats._norm_check(vals) for lbl, vals in kept}
                # a group counts as non-normal only when it was actually testable (n >= 3)
                normal = all(v.get("looks_normal") is not False for v in normality_summary.values())
                if len(kept) == 2:
                    suggested = "ttest_independent" if normal else "mann_whitney"
                else:
                    suggested = "anova_oneway" if normal else "kruskal_wallis"
                if excluded:
                    group_summary = group_summary + [{"group": e["group"], "n": e["n"], "excluded": True}
                                                     for e in excluded]

    return {
        "suggested_test": suggested,
        "justification": WIZARD_JUSTIFICATIONS[suggested],
        "alternative_test": WIZARD_ALTERNATIVES[suggested],
        "group_summary": group_summary,
        "normality_summary": normality_summary,
    }


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
        out = {
            "id": row["id"],
            "analysis_type": row["analysis_type"],
            "data_source": row["data_source"],
            "created_at": row["created_at"],
            **json.loads(row["result_json"]),
        }
        if row["interpretation_json"]:
            out["interpretation"] = json.loads(row["interpretation_json"])
        return out


# ── AI interpretation (36C-3): 3 credits, guard-checked, snapshot ─

class InterpretBody(BaseModel):
    language: Optional[str] = None  # 'ms' | 'en'; default from project output_language


@router.post("/analyses/{analysis_id}/interpret")
async def interpret_analysis(analysis_id: int, body: InterpretBody, user=Depends(get_current_user)):
    with get_db() as db:
        row = db.execute(
            """SELECT a.*, u.tier, u.kredit_remaining, p.output_language
               FROM survey_analyses a
               JOIN surveys s ON s.id = a.survey_id
               JOIN projects p ON p.id = s.project_id
               JOIN users u ON u.id = p.user_id
               WHERE a.id=? AND p.user_id=?""",
            (analysis_id, user["user_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Analysis not found.")
        if row["tier"] != "pro":
            raise HTTPException(403, "The Survey module is available on the Pro plan only.")
        if row["kredit_remaining"] < interpretation_guard.INTERPRET_COST:
            raise HTTPException(402, "Insufficient Research Credits.")
        if body.language is not None and body.language not in ("ms", "en"):
            raise HTTPException(422, "language must be 'ms' or 'en'.")
        language = body.language or ("ms" if row["output_language"] == "bm" else "en")
        result_json = json.loads(row["result_json"])
        analysis_type = row["analysis_type"]

    # LLM call outside the DB context; credits are deducted ONLY after the
    # narrative passes the anti-hallucination post-check (36A pattern).
    try:
        narrative = await interpretation_guard.generate_interpretation(
            result_json, analysis_type, language)
    except interpretation_guard.InterpretationRejected:
        raise HTTPException(
            502, "Interpretation failed validation: the AI produced numbers not present in "
                 "your results. No credits were deducted — please try again.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            502, "Interpretation generation failed. No credits were deducted — please try again.")

    generated_at = datetime.utcnow().isoformat()
    interpretation = {"language": language, "narrative": narrative, "generated_at": generated_at}
    with get_db() as db:
        try:
            new_kredit = deduct_credits(db, user["user_id"], interpretation_guard.INTERPRET_COST)
        except ValueError:
            raise HTTPException(402, "Insufficient Research Credits.")
        db.execute("UPDATE survey_analyses SET interpretation_json=? WHERE id=?",
                   (json.dumps(interpretation), analysis_id))
    return {
        "analysis_id": analysis_id,
        **interpretation,
        "kredit_used": interpretation_guard.INTERPRET_COST,
        "kredit_remaining": new_kredit,
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
