import json
import re
from typing import Dict, List

from app.services.embedding_pool import embedding_pool
from app.services.rag_pipeline import retrieve_chunks
from app.services.llm_provider import call_deepseek_raw

ALLOWED_TYPES = {"likert", "mcq", "open", "demographic"}

_PROMPT_TEMPLATE = """Anda adalah pembantu penyelidikan yang menjana DRAF instrumen soal selidik untuk pelajar pascasiswazah Malaysia.

KONTEKS DARI DOKUMEN PROJEK PENGGUNA (objektif kajian, kerangka konsep, pemboleh ubah, hipotesis):
{context}

{instruction_block}ARAHAN:
1. Jana draf instrumen soal selidik berdasarkan konteks di atas SAHAJA.
2. Bahasa soalan: {language}.
3. Ikut struktur lazim tesis Malaysia: Bahagian A Demografi, kemudian Bahagian B dan seterusnya untuk setiap konstruk/pemboleh ubah.
4. Skala Likert: default 5 mata melainkan dokumen menyatakan sebaliknya.
5. question_type mesti salah satu: "likert", "mcq", "open", "demographic".
6. Untuk likert: options = label skala (cth ["Sangat Tidak Setuju", "Tidak Setuju", "Tidak Pasti", "Setuju", "Sangat Setuju"]), likert_points = bilangan mata.
7. Untuk mcq/demographic: options = senarai pilihan. Untuk open: options = null, likert_points = null.
8. Ini DRAF sahaja — jangan tulis apa-apa dakwaan kesahan atau kebolehpercayaan instrumen.

WAJIB: Balas dengan JSON SAHAJA, tiada teks lain, ikut struktur tepat ini:
{{"sections": [{{"title": "...", "questions": [{{"question_text": "...", "question_type": "likert", "options": ["..."], "likert_points": 5}}]}}]}}"""


async def get_project_context(project_id: str) -> str:
    """Retrieve grounding context from project chunks via existing RAG pipeline."""
    query = "objektif kajian, conceptual framework, pemboleh ubah, hipotesis, kerangka konsep"
    query_embedding = await embedding_pool.embed(query)
    chunks = await retrieve_chunks(project_id, query_embedding, query_type="deep")
    return "\n\n".join(c["text"] for c in chunks)


def _parse_llm_json(raw: str) -> Dict:
    """Strip markdown fences and parse. Raises ValueError on bad structure."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    data = json.loads(text)
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("JSON tiada senarai sections")
    normalized: List[Dict] = []
    for sec in sections:
        title = str(sec.get("title", "")).strip()
        questions = sec.get("questions")
        if not title or not isinstance(questions, list):
            raise ValueError("Section tidak lengkap")
        norm_qs = []
        for q in questions:
            qtext = str(q.get("question_text", "")).strip()
            qtype = str(q.get("question_type", "open")).strip()
            if not qtext:
                raise ValueError("Soalan kosong")
            if qtype not in ALLOWED_TYPES:
                qtype = "open"
            options = q.get("options")
            likert_points = q.get("likert_points")
            if qtype == "open":
                options, likert_points = None, None
            norm_qs.append({
                "question_text": qtext,
                "question_type": qtype,
                "options": options if isinstance(options, list) else None,
                "likert_points": int(likert_points) if likert_points else None,
            })
        normalized.append({"title": title, "questions": norm_qs})
    return {"sections": normalized}


async def generate_survey_content(
    project_id: str,
    output_language: str = "bm",
    scope: str = "full",
    instruction: str = "",
) -> Dict:
    """Generate instrument draft. Raises ValueError if LLM output unparseable
    after one retry — caller must NOT deduct credits in that case."""
    context = await get_project_context(project_id)
    language = "Bahasa Malaysia" if output_language == "bm" else "English"
    instruction_block = ""
    if scope == "section" and instruction:
        instruction_block = f"FOKUS: jana SATU bahagian sahaja mengikut arahan pengguna ini: {instruction}\n\n"

    prompt = _PROMPT_TEMPLATE.format(
        context=context[:12000],
        language=language,
        instruction_block=instruction_block,
    )

    last_error = None
    for _ in range(2):  # ponytail: retry SEKALI ikut brief, kemudian error jelas
        raw = await call_deepseek_raw(prompt, max_tokens=4096)
        try:
            return _parse_llm_json(raw)
        except (ValueError, json.JSONDecodeError, TypeError) as e:
            last_error = e
    raise ValueError(f"AI gagal jana JSON yang sah: {last_error}")
