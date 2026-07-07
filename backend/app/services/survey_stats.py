"""
Statistics engine for survey analysis (36C-1 descriptive/reliability/normality,
36C-2 inferential). Pure Python/pandas/scipy — no LLM.

Every function returns a JSON-serialisable dict with an `apa_table` block
({title, columns, rows, note}) that both the frontend and the docx exporter
render from — one source of truth. Floats are rounded to 3 decimals in output.

36C-2 additions: group comparisons (t-test/ANOVA + non-parametric fallbacks),
paired tests, correlation matrix, chi-square. Every inferential result carries
`apa_sentence` (static f-string template, APA number formatting), automatic
`assumption_checks` (reported, never blocking) and a manual-formula effect size
with a Cohen convention band label.
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


# ═════════════════════════════════════════════════════════════════
# 36C-2 — Inferential engine
# ═════════════════════════════════════════════════════════════════

def _p_apa(p) -> str:
    """APA p-value string: 'p < .001' below .001, else 'p = .024' (no leading 0)."""
    if p is None:
        return "p = n/a"
    if p < 0.001:
        return "p < .001"
    s = f"{p:.3f}"
    if s.startswith("0."):
        s = s[1:]
    return f"p = {s}"


def _fmt_df(v) -> str:
    """Degrees of freedom: integer when whole, else 2 decimals (Welch)."""
    vf = float(v)
    return str(int(vf)) if vf == int(vf) else f"{vf:.2f}"


def _band_d(d):
    a = abs(d)
    return "negligible" if a < 0.2 else "small" if a < 0.5 else "medium" if a < 0.8 else "large"


def _band_eta2(e):
    return "negligible" if e < 0.01 else "small" if e < 0.06 else "medium" if e < 0.14 else "large"


def _band_r(r):
    a = abs(r)
    return "negligible" if a < 0.1 else "small" if a < 0.3 else "medium" if a < 0.5 else "large"


def _band_v(v, df_min):
    """Cramér's V bands per Cohen, adjusted by min(r,c)-1."""
    cuts = {1: (0.1, 0.3, 0.5), 2: (0.07, 0.21, 0.35)}.get(df_min, (0.06, 0.17, 0.29))
    return "negligible" if v < cuts[0] else "small" if v < cuts[1] else "medium" if v < cuts[2] else "large"


def _z_from_p(p) -> float:
    """|Z| consistent with a two-sided p (for Mann-Whitney/Wilcoxon r = Z/√N)."""
    if p is None or p >= 1:
        return 0.0
    return float(abs(stats.norm.isf(p / 2)))


def _norm_check(x) -> dict:
    """Normality summary for assumption checks (36C-1 logic; never raises)."""
    x = np.asarray(x, dtype=float)
    n = int(x.shape[0])
    if n < 3:
        return {"n": n, "skewness": None, "kurtosis": None,
                "shapiro_w": None, "shapiro_p": None, "looks_normal": None}
    skew = float(stats.skew(x, bias=False))
    kurt = float(stats.kurtosis(x, fisher=True, bias=False))
    w, p = stats.shapiro(x)
    return {"n": n, "skewness": _r(skew), "kurtosis": _r(kurt),
            "shapiro_w": _r(w), "shapiro_p": _r(p),
            "looks_normal": bool(abs(skew) < 1 and abs(kurt) < 1 and p > 0.05)}


def build_groups(df: pd.DataFrame, meta: dict, outcome: pd.Series, grouping_qid: int):
    """Split the outcome series by a categorical grouping question.

    Returns (kept, excluded, group_summary):
      kept     = [(label, np.ndarray), ...] groups with n >= 2
      excluded = [{"group", "n"}, ...] groups with n < 2 (reported, not used)
    """
    qm = meta.get(grouping_qid)
    if not qm:
        raise HTTPException(422, "Grouping question does not belong to this survey.")
    if qm["type"] not in ("mcq", "demographic"):
        raise HTTPException(422, "Grouping question must be an MCQ or demographic question.")
    sub = pd.concat([outcome.rename("y"), df[grouping_qid].rename("g")], axis=1, join="inner").dropna()
    options = qm["options"] or sorted(sub["g"].unique().tolist())
    kept, excluded, summary = [], [], []
    for opt in options:
        vals = sub.loc[sub["g"] == opt, "y"].to_numpy(dtype=float)
        n = int(vals.shape[0])
        if n < 2:
            excluded.append({"group": str(opt), "n": n})
            continue
        kept.append((str(opt), vals))
        summary.append({"group": str(opt), "n": n, "mean": _r(vals.mean()),
                        "sd": _r(vals.std(ddof=1)), "median": _r(float(np.median(vals)))})
    if len(kept) < 2:
        raise HTTPException(422, "Need at least 2 groups with 2 or more responses each.")
    return kept, excluded, summary


def _group_assumptions(kept) -> dict:
    lev = stats.levene(*[g[1] for g in kept])
    return {
        "levene": {"statistic": _r(float(lev.statistic)), "p": _r(float(lev.pvalue))},
        "normality_per_group": {label: _norm_check(vals) for label, vals in kept},
    }


def _group_apa_table(title: str, summary, note: str) -> dict:
    return {
        "title": title,
        "columns": ["Group", "n", "M", "SD", "Mdn"],
        "rows": [[g["group"], g["n"], g["mean"], g["sd"], g["median"]] for g in summary],
        "note": note,
    }


def run_ttest_independent(df, meta, outcome_label: str, outcome: pd.Series,
                          grouping_qid: int, grouping_label: str) -> dict:
    kept, excluded, summary = build_groups(df, meta, outcome, grouping_qid)
    if len(kept) != 2:
        raise HTTPException(422, f"Independent t-test requires exactly 2 groups (found {len(kept)}). "
                                 "Use one-way ANOVA for 3 or more groups.")
    checks = _group_assumptions(kept)
    welch = checks["levene"]["p"] is not None and checks["levene"]["p"] < 0.05
    (la, a), (lb, b) = kept
    res = stats.ttest_ind(a, b, equal_var=not welch)
    n1, n2 = a.shape[0], b.shape[0]
    # Cohen's d with pooled SD (reported for Welch too, by convention)
    sp = np.sqrt(((n1 - 1) * a.var(ddof=1) + (n2 - 1) * b.var(ddof=1)) / (n1 + n2 - 2))
    d = float((a.mean() - b.mean()) / sp) if sp > 0 else 0.0
    sig = "a significant" if res.pvalue < 0.05 else "no significant"
    test_name = "Welch's t-test" if welch else "independent samples t-test"
    sentence = (f"There was {sig} difference in {outcome_label} between {la} "
                f"(M = {a.mean():.2f}, SD = {a.std(ddof=1):.2f}) and {lb} "
                f"(M = {b.mean():.2f}, SD = {b.std(ddof=1):.2f}), "
                f"t({_fmt_df(res.df)}) = {res.statistic:.2f}, {_p_apa(res.pvalue)}, d = {d:.2f}.")
    note = sentence
    if welch:
        note += " Levene's test indicated unequal variances; Welch's t-test is reported."
    result = {
        "test": "ttest_independent", "test_name": test_name,
        "outcome": outcome_label, "grouping": grouping_label,
        "groups": summary, "excluded_groups": excluded,
        "statistic": _r(float(res.statistic)), "df": _r(float(res.df)),
        "p": _r(float(res.pvalue), 6), "welch_applied": bool(welch),
        "effect_size": {"name": "Cohen's d", "value": _r(d), "band": _band_d(d)},
        "assumption_checks": checks,
        "apa_sentence": sentence,
        "apa_table": _group_apa_table(f"Independent Samples t-Test — {outcome_label} by {grouping_label}",
                                      summary, note),
    }
    return result


def run_anova_oneway(df, meta, outcome_label: str, outcome: pd.Series,
                     grouping_qid: int, grouping_label: str) -> dict:
    kept, excluded, summary = build_groups(df, meta, outcome, grouping_qid)
    checks = _group_assumptions(kept)
    arrays = [g[1] for g in kept]
    res = stats.f_oneway(*arrays)
    allv = np.concatenate(arrays)
    grand = allv.mean()
    ss_between = sum(len(x) * (x.mean() - grand) ** 2 for x in arrays)
    ss_total = float(((allv - grand) ** 2).sum())
    eta2 = float(ss_between / ss_total) if ss_total > 0 else 0.0
    df1, df2 = len(kept) - 1, allv.shape[0] - len(kept)
    sig = "a significant" if res.pvalue < 0.05 else "no significant"
    sentence = (f"There was {sig} difference in {outcome_label} between groups, "
                f"F({df1}, {df2}) = {res.statistic:.2f}, {_p_apa(res.pvalue)}, η² = {eta2:.2f}.")
    note = sentence
    if checks["levene"]["p"] is not None and checks["levene"]["p"] < 0.05:
        note += " Levene's test indicated unequal variances; consider the non-parametric Kruskal-Wallis test."
    tukey = stats.tukey_hsd(*arrays)
    labels = [g[0] for g in kept]
    pairs = []
    for i in range(len(kept)):
        for j in range(i + 1, len(kept)):
            pairs.append({"group_a": labels[i], "group_b": labels[j],
                          "mean_diff": _r(float(arrays[i].mean() - arrays[j].mean())),
                          "p": _r(float(tukey.pvalue[i, j]), 6)})
    posthoc_table = {
        "title": f"Tukey HSD Post-Hoc Comparisons — {outcome_label} by {grouping_label}",
        "columns": ["Comparison", "Mean Difference", "p"],
        "rows": [[f"{p['group_a']} vs {p['group_b']}", p["mean_diff"], p["p"]] for p in pairs],
        "note": "Tukey HSD controls the family-wise error rate across pairwise comparisons.",
    }
    return {
        "test": "anova_oneway", "test_name": "one-way ANOVA",
        "outcome": outcome_label, "grouping": grouping_label,
        "groups": summary, "excluded_groups": excluded,
        "statistic": _r(float(res.statistic)), "df_between": df1, "df_within": df2,
        "p": _r(float(res.pvalue), 6),
        "effect_size": {"name": "eta-squared", "value": _r(eta2), "band": _band_eta2(eta2)},
        "assumption_checks": checks, "posthoc": pairs,
        "apa_sentence": sentence,
        "apa_table": _group_apa_table(f"One-Way ANOVA — {outcome_label} by {grouping_label}", summary, note),
        "posthoc_apa_table": posthoc_table,
    }


def run_mann_whitney(df, meta, outcome_label: str, outcome: pd.Series,
                     grouping_qid: int, grouping_label: str) -> dict:
    kept, excluded, summary = build_groups(df, meta, outcome, grouping_qid)
    if len(kept) != 2:
        raise HTTPException(422, f"Mann-Whitney U requires exactly 2 groups (found {len(kept)}). "
                                 "Use Kruskal-Wallis for 3 or more groups.")
    checks = _group_assumptions(kept)
    (la, a), (lb, b) = kept
    res = stats.mannwhitneyu(a, b, alternative="two-sided")
    n = a.shape[0] + b.shape[0]
    z = _z_from_p(float(res.pvalue))
    r_eff = float(z / np.sqrt(n))
    sig = "a significant" if res.pvalue < 0.05 else "no significant"
    sentence = (f"A Mann-Whitney U test indicated {sig} difference in {outcome_label} between "
                f"{la} (Mdn = {np.median(a):.2f}) and {lb} (Mdn = {np.median(b):.2f}), "
                f"U = {res.statistic:.1f}, {_p_apa(res.pvalue)}, r = {r_eff:.2f}.")
    return {
        "test": "mann_whitney", "test_name": "Mann-Whitney U test",
        "outcome": outcome_label, "grouping": grouping_label,
        "groups": summary, "excluded_groups": excluded,
        "statistic": _r(float(res.statistic)), "p": _r(float(res.pvalue), 6), "z": _r(z),
        "effect_size": {"name": "r", "value": _r(r_eff), "band": _band_r(r_eff)},
        "assumption_checks": checks,
        "apa_sentence": sentence,
        "apa_table": _group_apa_table(f"Mann-Whitney U Test — {outcome_label} by {grouping_label}",
                                      summary, sentence + " r = Z/√N."),
    }


def run_kruskal_wallis(df, meta, outcome_label: str, outcome: pd.Series,
                       grouping_qid: int, grouping_label: str) -> dict:
    kept, excluded, summary = build_groups(df, meta, outcome, grouping_qid)
    checks = _group_assumptions(kept)
    arrays = [g[1] for g in kept]
    res = stats.kruskal(*arrays)
    dfree = len(kept) - 1
    sig = "a significant" if res.pvalue < 0.05 else "no significant"
    sentence = (f"A Kruskal-Wallis test indicated {sig} difference in {outcome_label} between groups, "
                f"H({dfree}) = {res.statistic:.2f}, {_p_apa(res.pvalue)}.")
    return {
        "test": "kruskal_wallis", "test_name": "Kruskal-Wallis test",
        "outcome": outcome_label, "grouping": grouping_label,
        "groups": summary, "excluded_groups": excluded,
        "statistic": _r(float(res.statistic)), "df": dfree, "p": _r(float(res.pvalue), 6),
        "assumption_checks": checks,
        "apa_sentence": sentence,
        "apa_table": _group_apa_table(f"Kruskal-Wallis Test — {outcome_label} by {grouping_label}",
                                      summary, sentence),
    }


def run_paired_test(kind: str, label_a: str, series_a: pd.Series,
                    label_b: str, series_b: pd.Series) -> dict:
    """Paired t-test or Wilcoxon signed-rank on two variables (listwise pairs)."""
    pairs = pd.concat([series_a.rename("a"), series_b.rename("b")], axis=1, join="inner").dropna()
    n = int(pairs.shape[0])
    if n < 3:
        raise HTTPException(422, "Need at least 3 complete pairs for a paired test.")
    a = pairs["a"].to_numpy(dtype=float)
    b = pairs["b"].to_numpy(dtype=float)
    diff = a - b
    var_rows = [
        {"variable": label_a, "n": n, "mean": _r(a.mean()), "sd": _r(a.std(ddof=1))},
        {"variable": label_b, "n": n, "mean": _r(b.mean()), "sd": _r(b.std(ddof=1))},
    ]
    checks = {"normality_of_differences": _norm_check(diff)}
    if kind == "ttest_paired":
        res = stats.ttest_rel(a, b)
        sd_diff = diff.std(ddof=1)
        d = float(diff.mean() / sd_diff) if sd_diff > 0 else 0.0
        sig = "a significant" if res.pvalue < 0.05 else "no significant"
        sentence = (f"There was {sig} difference between {label_a} (M = {a.mean():.2f}, SD = {a.std(ddof=1):.2f}) "
                    f"and {label_b} (M = {b.mean():.2f}, SD = {b.std(ddof=1):.2f}), "
                    f"t({n - 1}) = {res.statistic:.2f}, {_p_apa(res.pvalue)}, d = {d:.2f}.")
        result = {
            "test": "ttest_paired", "test_name": "paired samples t-test",
            "statistic": _r(float(res.statistic)), "df": n - 1, "p": _r(float(res.pvalue), 6),
            "effect_size": {"name": "Cohen's d", "value": _r(d), "band": _band_d(d)},
        }
        title = f"Paired Samples t-Test — {label_a} vs {label_b}"
    else:  # wilcoxon
        try:
            res = stats.wilcoxon(a, b)
        except ValueError:
            raise HTTPException(422, "All paired differences are zero; the Wilcoxon test cannot be computed.")
        z = _z_from_p(float(res.pvalue))
        r_eff = float(z / np.sqrt(n))
        sig = "a significant" if res.pvalue < 0.05 else "no significant"
        sentence = (f"A Wilcoxon signed-rank test indicated {sig} difference between {label_a} "
                    f"(Mdn = {np.median(a):.2f}) and {label_b} (Mdn = {np.median(b):.2f}), "
                    f"W = {res.statistic:.1f}, {_p_apa(res.pvalue)}, r = {r_eff:.2f}.")
        result = {
            "test": "wilcoxon", "test_name": "Wilcoxon signed-rank test",
            "statistic": _r(float(res.statistic)), "p": _r(float(res.pvalue), 6), "z": _r(z),
            "effect_size": {"name": "r", "value": _r(r_eff), "band": _band_r(r_eff)},
        }
        title = f"Wilcoxon Signed-Rank Test — {label_a} vs {label_b}"
    result.update({
        "variable_a": label_a, "variable_b": label_b, "n_pairs": n,
        "variables": var_rows, "assumption_checks": checks, "apa_sentence": sentence,
        "apa_table": {
            "title": title,
            "columns": ["Variable", "n", "M", "SD"],
            "rows": [[v["variable"], v["n"], v["mean"], v["sd"]] for v in var_rows],
            "note": sentence + " Pairs are matched listwise (rows with both values present).",
        },
    })
    return result


def _sig_marker(p) -> str:
    if p is None:
        return ""
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else ""


def run_correlation(variables) -> dict:
    """Pearson + Spearman matrix over 2+ numeric variables [(label, series), ...]."""
    if len(variables) < 2:
        raise HTTPException(422, "Correlation analysis requires at least 2 numeric variables.")
    labels = [v[0] for v in variables]
    if len(set(labels)) != len(labels):
        raise HTTPException(422, "Correlation variables must be distinct.")
    cells = {}
    for i in range(len(variables)):
        for j in range(i + 1, len(variables)):
            (la, sa), (lb, sb) = variables[i], variables[j]
            pairs = pd.concat([sa.rename("a"), sb.rename("b")], axis=1, join="inner").dropna()
            n = int(pairs.shape[0])
            if n < 3:
                cells[(i, j)] = {"n": n, "pearson_r": None, "pearson_p": None,
                                 "spearman_rho": None, "spearman_p": None}
                continue
            pr = stats.pearsonr(pairs["a"], pairs["b"])
            sr = stats.spearmanr(pairs["a"], pairs["b"])
            cells[(i, j)] = {"n": n,
                             "pearson_r": _r(float(pr.statistic)), "pearson_p": _r(float(pr.pvalue), 6),
                             "spearman_rho": _r(float(sr.statistic)), "spearman_p": _r(float(sr.pvalue), 6)}
    pair_list = [{"variable_a": labels[i], "variable_b": labels[j], **c} for (i, j), c in cells.items()]

    def matrix_table(title, key_r, key_p):
        rows = []
        for i, la in enumerate(labels):
            row = [la]
            for j in range(len(labels)):
                if i == j:
                    row.append("—")
                else:
                    c = cells.get((min(i, j), max(i, j)))
                    r_val = c[key_r]
                    row.append("" if r_val is None else f"{r_val:.3f}{_sig_marker(c[key_p])}")
            rows.append(row)
        return {"title": title, "columns": ["Variable", *labels], "rows": rows,
                "note": "* p < .05, ** p < .01, *** p < .001 (two-tailed). Pairwise deletion of missing values."}

    if len(variables) == 2:
        c = cells[(0, 1)]
        if c["pearson_r"] is None:
            sentence = f"Too few complete pairs (n = {c['n']}) to estimate the correlation between {labels[0]} and {labels[1]}."
        else:
            direction = "positive" if c["pearson_r"] >= 0 else "negative"
            sig = "a significant" if (c["pearson_p"] is not None and c["pearson_p"] < 0.05) else "no significant"
            sentence = (f"There was {sig} {direction} correlation between {labels[0]} and {labels[1]}, "
                        f"r({c['n'] - 2}) = {c['pearson_r']:.2f}, {_p_apa(c['pearson_p'])}.")
    else:
        rs = [c["pearson_r"] for c in cells.values() if c["pearson_r"] is not None]
        if rs:
            sentence = (f"Pearson correlations across the {len(labels)} variables ranged from "
                        f"r = {min(rs):.2f} to r = {max(rs):.2f}; see the correlation matrix for significance.")
        else:
            sentence = "Too few complete pairs to estimate correlations; see the matrix."
    return {
        "test": "correlation", "test_name": "correlation analysis",
        "variables": labels, "pairs": pair_list,
        "apa_sentence": sentence,
        "apa_table": matrix_table("Pearson Correlation Matrix", "pearson_r", "pearson_p"),
        "spearman_apa_table": matrix_table("Spearman Correlation Matrix", "spearman_rho", "spearman_p"),
    }


def run_chi_square(df: pd.DataFrame, meta: dict, qid_a: int, qid_b: int) -> dict:
    for qid in (qid_a, qid_b):
        qm = meta.get(qid)
        if not qm:
            raise HTTPException(422, "Chi-square question does not belong to this survey.")
        if qm["type"] not in ("mcq", "demographic"):
            raise HTTPException(422, "Chi-square requires two categorical (MCQ or demographic) questions.")
    if qid_a == qid_b:
        raise HTTPException(422, "Chi-square requires two different questions.")
    sub = df[[qid_a, qid_b]].dropna()
    if sub.shape[0] < 2:
        raise HTTPException(422, "Not enough paired responses for a chi-square test.")
    crosstab = pd.crosstab(sub[qid_a], sub[qid_b])
    if crosstab.shape[0] < 2 or crosstab.shape[1] < 2:
        raise HTTPException(422, "Chi-square needs at least 2 observed categories per question.")
    obs = crosstab.to_numpy()
    res = stats.chi2_contingency(obs, correction=False)
    n = int(obs.sum())
    df_min = min(obs.shape) - 1
    v = float(np.sqrt(res.statistic / (n * df_min))) if n * df_min > 0 else 0.0
    low_frac = float((res.expected_freq < 5).sum() / res.expected_freq.size)
    warning = None
    if low_frac > 0.2:
        warning = ("More than 20% of cells have an expected count below 5; "
                   "chi-square results may be unreliable.")
    label_a, label_b = f"Q{qid_a}", f"Q{qid_b}"
    sig = "significant" if res.pvalue < 0.05 else "not significant"
    sentence = (f"The association between {label_a} and {label_b} was {sig}, "
                f"χ²({res.dof}, N = {n}) = {res.statistic:.2f}, {_p_apa(res.pvalue)}, V = {v:.2f}.")
    note = sentence + " Chi-square computed without Yates continuity correction."
    if warning:
        note += " " + warning
    apa = {
        "title": f"Crosstabulation — {label_a} × {label_b}",
        "columns": [f"{label_a} \\ {label_b}", *[str(c) for c in crosstab.columns]],
        "rows": [[str(idx), *[int(x) for x in row]] for idx, row in zip(crosstab.index, obs)],
        "note": note,
    }
    return {
        "test": "chi_square", "test_name": "chi-square test of independence",
        "question_a": qid_a, "question_b": qid_b, "n": n,
        "statistic": _r(float(res.statistic)), "df": int(res.dof), "p": _r(float(res.pvalue), 6),
        "effect_size": {"name": "Cramér's V", "value": _r(v), "band": _band_v(v, df_min)},
        "observed": {str(idx): {str(c): int(x) for c, x in zip(crosstab.columns, row)}
                     for idx, row in zip(crosstab.index, obs)},
        "expected_low_fraction": _r(low_frac),
        "warning": warning,
        "apa_sentence": sentence,
        "apa_table": apa,
    }
