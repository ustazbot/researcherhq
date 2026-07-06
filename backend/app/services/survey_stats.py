"""
Statistics engine for survey analysis (36C-1). Pure Python/pandas/scipy — no LLM.

Every function returns a JSON-serialisable dict with an `apa_table` block
({title, columns, rows, note}) that both the frontend and the docx exporter
render from — one source of truth. Floats are rounded to 3 decimals in output.
"""
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy import stats
from fastapi import HTTPException


def _r(x, nd: int = 3):
    """Round to nd decimals, return a plain float; None/NaN -> None."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    if np.isnan(xf) or np.isinf(xf):
        return None
    return round(xf, nd)


# ── Descriptive ──────────────────────────────────────────────────

def run_descriptive(df: pd.DataFrame, meta: dict,
                    question_ids: List[int], constructs: Optional[List[dict]] = None) -> dict:
    items = []
    for qid in question_ids:
        qm = meta[qid]
        col = df[qid]
        non_missing = col.dropna()
        n = int(non_missing.shape[0])
        missing = int(col.shape[0] - n)
        entry = {"question_id": qid, "type": qm["type"], "n": n, "missing": missing}
        if qm["type"] == "likert":
            numeric = pd.to_numeric(non_missing, errors="coerce").dropna()
            entry["mean"] = _r(numeric.mean())
            entry["sd"] = _r(numeric.std(ddof=1)) if n > 1 else None
            entry["min"] = _r(numeric.min()) if n else None
            entry["max"] = _r(numeric.max()) if n else None
            points = qm["likert_points"] or 5
            freq = {str(p): int((numeric == p).sum()) for p in range(1, points + 1)}
            entry["frequency"] = freq
        else:  # mcq / demographic — frequency per option label
            options = qm["options"] or sorted(non_missing.unique().tolist())
            freq = {str(opt): int((non_missing == opt).sum()) for opt in options}
            entry["frequency"] = freq
            entry["percent"] = {k: _r(100 * v / n) if n else None for k, v in freq.items()}
        items.append(entry)

    construct_rows = []
    for c in (constructs or []):
        sub = df[c["items"]].dropna()
        comp = sub.mean(axis=1) if sub.shape[0] else pd.Series(dtype=float)
        construct_rows.append({
            "name": c["name"],
            "n": int(sub.shape[0]),
            "mean": _r(comp.mean()) if sub.shape[0] else None,
            "sd": _r(comp.std(ddof=1)) if sub.shape[0] > 1 else None,
            "min": _r(comp.min()) if sub.shape[0] else None,
            "max": _r(comp.max()) if sub.shape[0] else None,
        })

    # APA table — construct composites if present, else per-item likert summary
    if construct_rows:
        apa = {
            "title": "Descriptive Statistics of Study Constructs",
            "columns": ["Construct", "n", "M", "SD", "Min", "Max"],
            "rows": [[c["name"], c["n"], c["mean"], c["sd"], c["min"], c["max"]] for c in construct_rows],
            "note": "M = mean composite score; SD = standard deviation (n-1).",
        }
    else:
        likert_items = [it for it in items if it["type"] == "likert"]
        apa = {
            "title": "Descriptive Statistics",
            "columns": ["Item", "n", "M", "SD", "Min", "Max"],
            "rows": [[f"Q{it['question_id']}", it["n"], it.get("mean"), it.get("sd"), it.get("min"), it.get("max")]
                     for it in likert_items],
            "note": "SD uses n-1 denominator.",
        }
    return {"items": items, "constructs": construct_rows, "apa_table": apa}


# ── Reliability (Cronbach's alpha) ───────────────────────────────

def _cronbach_alpha(sub: pd.DataFrame) -> Optional[float]:
    """α = (k/(k-1)) · (1 − Σ s²ᵢ / s²ₜ). ddof=1 variances. sub already listwise."""
    k = sub.shape[1]
    if k < 2 or sub.shape[0] < 2:
        return None
    item_var_sum = sub.var(ddof=1).sum()
    total_var = sub.sum(axis=1).var(ddof=1)
    if total_var == 0:
        return None
    return (k / (k - 1)) * (1 - item_var_sum / total_var)


def run_reliability(df: pd.DataFrame, construct_items: List[int], construct_name: str) -> dict:
    if len(construct_items) < 2:
        raise HTTPException(422, "A construct needs at least 2 items for reliability analysis.")
    sub = df[construct_items].dropna()  # listwise
    n = int(sub.shape[0])
    if n < 2:
        raise HTTPException(422, "Not enough complete responses for reliability analysis.")

    alpha = _cronbach_alpha(sub)
    total = sub.sum(axis=1)

    per_item = []
    for qid in construct_items:
        remaining = [q for q in construct_items if q != qid]
        alpha_del = _cronbach_alpha(sub[remaining]) if len(remaining) >= 2 else None
        # corrected item-total correlation: item vs sum of OTHER items
        others_total = total - sub[qid]
        if sub[qid].std(ddof=1) == 0 or others_total.std(ddof=1) == 0:
            itc = None
        else:
            itc = sub[qid].corr(others_total)
        per_item.append({
            "question_id": qid,
            "alpha_if_deleted": _r(alpha_del),
            "corrected_item_total_correlation": _r(itc),
        })

    apa = {
        "title": f"Reliability Analysis — {construct_name}",
        "columns": ["Item", "Corrected Item-Total r", "α if Item Deleted"],
        "rows": [[f"Q{p['question_id']}", p["corrected_item_total_correlation"], p["alpha_if_deleted"]]
                 for p in per_item],
        "note": f"Cronbach's α = {_r(alpha)} ({len(construct_items)} items, n = {n}, listwise).",
    }
    return {
        "construct": construct_name,
        "n": n,
        "k": len(construct_items),
        "cronbach_alpha": _r(alpha),
        "items": per_item,
        "apa_table": apa,
    }


# ── Normality ────────────────────────────────────────────────────

def run_normality(df: pd.DataFrame, meta: dict,
                 item_qid: Optional[int] = None, construct: Optional[dict] = None) -> dict:
    if construct is not None:
        sub = df[construct["items"]].dropna()
        series = sub.mean(axis=1)
        label = construct["name"]
    elif item_qid is not None:
        series = pd.to_numeric(df[item_qid], errors="coerce").dropna()
        label = f"Q{item_qid}"
    else:
        raise HTTPException(422, "Provide either a construct or a likert item for normality.")

    x = series.to_numpy(dtype=float)
    n = int(x.shape[0])
    if n < 3:
        raise HTTPException(422, "Need at least 3 valid values for a normality test.")

    # Fisher-Pearson standardized moment coefficients, bias-corrected
    skew = float(stats.skew(x, bias=False))
    kurt = float(stats.kurtosis(x, fisher=True, bias=False))  # excess kurtosis
    w, p = stats.shapiro(x)
    looks_normal = bool(abs(skew) < 1 and abs(kurt) < 1 and p > 0.05)

    apa = {
        "title": f"Normality Test — {label}",
        "columns": ["Target", "n", "Skewness", "Kurtosis", "Shapiro-Wilk W", "p"],
        "rows": [[label, n, _r(skew), _r(kurt), _r(w), _r(p)]],
        "note": "Skewness/kurtosis are bias-corrected; kurtosis is excess (0 = normal). "
                "'looks_normal' is a heuristic (|skew|<1, |kurtosis|<1, p>.05), not a definitive judgement.",
    }
    return {
        "target": label,
        "n": n,
        "skewness": _r(skew),
        "kurtosis": _r(kurt),
        "shapiro_w": _r(w),
        "shapiro_p": _r(p),
        "looks_normal": looks_normal,
        "apa_table": apa,
    }
