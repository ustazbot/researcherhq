"""
AI interpretation with anti-hallucination guard (36C-3).

The LLM writes the narrative; it is NEVER trusted with numbers. Every numeric
token in the output must already exist in the analysis result_json (allowing
rounding to 1-3 decimals, leading-zero variants, sign-magnitude mentions and
percent forms of proportions). One retry with a correction instruction, then
fail — the caller returns 502 and deducts no credits.

check_narrative() is a pure function: no LLM, no network, no DB.
"""
import json
import re
from typing import List, Set, Tuple

from app.services.llm_provider import call_deepseek_raw

INTERPRET_COST = 3

DISCLAIMER = {
    "en": "This interpretation was generated automatically. Verify with your supervisor before use.",
    "ms": "Interpretasi ini dijana secara automatik. Sahkan dengan penyelia anda sebelum digunakan.",
}


class InterpretationRejected(Exception):
    """Raised when the narrative fails the numeric post-check after retry."""
    def __init__(self, offending: List[str]):
        self.offending = offending
        super().__init__(f"Narrative contains numbers not present in the results: {offending}")


# ── Number collection from result_json ───────────────────────────

def _walk(obj, numbers: Set[float], p_values: Set[float], key=None):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        v = float(obj)
        numbers.add(v)
        if isinstance(key, str) and (key == "p" or key.endswith("_p") or key == "pvalue"):
            p_values.add(v)
        return
    if isinstance(obj, str):
        # matrix cells like "0.677***" carry result numbers inside strings
        for tok in _NUM_RE.findall(obj):
            try:
                numbers.add(float(_normalize(tok)))
            except ValueError:
                pass
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, numbers, p_values, key=k)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk(v, numbers, p_values, key=key)


def collect_allowed(result_json: dict) -> Tuple[Set[float], Set[float]]:
    """All numeric values in the result + the subset that are p-values.

    Expansion: |v| (magnitude mentions like 'a difference of 0.32' for t=-0.32)
    and v*100 for proportions |v|<=1 (percent mentions of eta²/r).
    """
    numbers: Set[float] = set()
    p_values: Set[float] = set()
    _walk(result_json, numbers, p_values)
    expanded = set()
    for v in numbers:
        expanded.add(v)
        expanded.add(abs(v))
        if abs(v) <= 1:
            expanded.add(round(v * 100, 6))
            expanded.add(round(abs(v) * 100, 6))
    return expanded, p_values


# ── Token extraction from the narrative ──────────────────────────

# fractions (.024), decimals (0.024, 15.65), integers (28), optional -/− sign
_NUM_RE = re.compile(r"[-−]?(?:\d+\.\d+|\.\d+|\d+)")
# 'p < .001' family — validated separately, then removed before token scan
_P_LT_RE = re.compile(r"p\s*<\s*0?\.001", re.IGNORECASE)


def _normalize(tok: str) -> str:
    tok = tok.replace("−", "-")
    if tok.startswith("."):
        tok = "0" + tok
    elif tok.startswith("-."):
        tok = "-0" + tok[1:]
    return tok


def _decimals(tok: str) -> int:
    return len(tok.split(".", 1)[1]) if "." in tok else 0


def check_narrative(narrative: str, result_json: dict) -> Tuple[bool, List[str]]:
    """Pure post-check. Returns (ok, offending_tokens).

    A token x is allowed when some result value v satisfies x == v or
    x == round(v, decimals(x)). 'p < .001' is allowed only when the result
    actually contains a p-value below .001.
    """
    numbers, p_values = collect_allowed(result_json)
    text = narrative

    if _P_LT_RE.search(text):
        if not any(p < 0.001 for p in p_values):
            return False, ["p < .001"]
        text = _P_LT_RE.sub(" ", text)

    offending = []
    for raw in _NUM_RE.findall(text):
        tok = _normalize(raw)
        try:
            x = float(tok)
        except ValueError:
            offending.append(raw)
            continue
        dp = min(_decimals(tok), 6)
        ok = any(x == v or x == round(v, dp) for v in numbers)
        if not ok:
            offending.append(raw)
    return (len(offending) == 0), offending


# ── Prompt + generation flow ─────────────────────────────────────

def _strip_tables(result_json: dict) -> dict:
    """Prompt payload without the APA table blocks (numbers duplicate the raw
    fields; the allowed-set is still built from the FULL result_json)."""
    def strip(obj):
        if isinstance(obj, dict):
            return {k: strip(v) for k, v in obj.items()
                    if k not in ("apa_table", "posthoc_apa_table", "spearman_apa_table", "apa_tables")}
        if isinstance(obj, list):
            return [strip(v) for v in obj]
        return obj
    return strip(result_json)


def build_prompt(result_json: dict, analysis_type: str, language: str,
                 correction: str = "") -> str:
    lang_line = ("Write the narrative in Bahasa Melayu (academic register)."
                 if language == "ms" else "Write the narrative in academic English.")
    return f"""You are writing a short results interpretation for a thesis (Chapter 4 style).

Analysis type: {analysis_type}
Analysis results (JSON):
{json.dumps(_strip_tables(result_json), ensure_ascii=False)}

STRICT RULES:
(a) Use ONLY numbers that appear in the JSON above. Do NOT compute, estimate or invent any number.
(b) Write small counts (below ten) as words, not digits.
(c) Output a 2-5 sentence academic narrative paragraph. No markdown headings, no bullet points.
(d) Interpret only what the results show (e.g. whether the difference or relationship is significant and its effect size). Do NOT draw conclusions beyond the results, give policy advice, or claim the study proves anything.
{lang_line}
{correction}
Output only the narrative paragraph."""


async def generate_interpretation(result_json: dict, analysis_type: str, language: str) -> str:
    """Generate + post-check, with one corrective retry. Returns the narrative
    WITH the static disclaimer appended (disclaimer added after the check so
    its wording is never part of the numeric validation)."""
    correction = ""
    offending: List[str] = []
    for _attempt in range(2):
        narrative = (await call_deepseek_raw(
            build_prompt(result_json, analysis_type, language, correction),
            max_tokens=500,
        )).strip()
        ok, offending = check_narrative(narrative, result_json)
        if ok:
            return f"{narrative}\n\n{DISCLAIMER.get(language, DISCLAIMER['en'])}"
        correction = ("IMPORTANT CORRECTION: your previous answer used numbers that are NOT in the "
                      f"JSON ({', '.join(offending[:10])}). Rewrite using only numbers from the JSON.")
    raise InterpretationRejected(offending)
