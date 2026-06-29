import json
from app.services.llm_provider import call_deepseek_raw

SV_EXTRACT_PROMPT = """You are a research assistant helping a postgraduate student track supervisor feedback.

Extract all specific, actionable feedback items from the supervisor notes below.

Rules:
- Each item must be one discrete, actionable piece of feedback
- Keep original meaning intact — do not paraphrase aggressively
- Ignore generic praise or filler ("Good work", "Overall okay")
- If notes are in Malay, keep items in Malay
- If notes are in English, keep items in English
- If mixed, keep each item in its original language

Return ONLY a valid JSON array of strings. No preamble, no markdown, no explanation.
Example: ["Revise citation format in Chapter 2", "Tambah justifikasi pemilihan sampel"]

If no actionable feedback found, return: []

Supervisor notes:
{text}"""


async def extract_sv_feedback(text: str) -> list[str]:
    """Extract discrete feedback items from supervisor notes using LLM."""
    if not text or len(text.strip()) < 20:
        return []

    # Truncate to ~4000 words to stay within token budget
    words = text.split()
    if len(words) > 4000:
        text = " ".join(words[:4000])

    prompt = SV_EXTRACT_PROMPT.format(text=text)
    try:
        raw = await call_deepseek_raw(prompt, max_tokens=800)
        raw = raw.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        items = json.loads(raw)
        if isinstance(items, list):
            return [str(i).strip() for i in items if str(i).strip()]
        return []
    except Exception:
        return []
