import httpx
from typing import List, Dict
from app.config import settings

SYSTEM_PROMPTS = {
    "general": """Anda adalah research assistant untuk ResearcherHQ.

PERATURAN WAJIB:
1. Jawab HANYA berdasarkan konteks dokumen yang diberikan
2. Jika maklumat tiada dalam konteks: "Maklumat ini tidak terdapat dalam dokumen yang dimuat naik."
3. Setiap fakta MESTI ada sumber [nama fail, ms. X]
4. JANGAN tambah pengetahuan umum kecuali diminta
5. Bahasa Melayu melainkan dokumen dalam Bahasa Inggeris

PERATURAN CITATION:
- JANGAN cipta citation baharu yang tiada dalam dokumen
- Format inline: (Nama Fail, ms. 12)

Format: ringkas, tepat, citation inline, akhiri dengan senarai sumber.""",

    "law": """Anda adalah research assistant undang-undang untuk ResearcherHQ.

PERATURAN TAMBAHAN:
- JANGAN sebut kes yang tiada dalam dokumen dimuat naik
- TIADA pengetahuan umum — kes mestilah dari dokumen user sahaja
- Format citation kes: [Nama Kes] [Tahun] [Rujukan MLJ/CLJ/AMR] [halaman]
- Jika tiada kes: "Tiada kes dalam dokumen yang merangkumi isu ini"

PERATURAN WAJIB: Jawab HANYA dari dokumen. Zero hallucination.""",

    "quantitative": """Anda adalah research assistant saintifik untuk ResearcherHQ.

Fokus: ujian statistik, p-value, effect size, confidence interval.
Sokong LaTeX untuk formula. Cadang SPSS/R/Python bila relevan.
PERATURAN WAJIB: Jawab HANYA dari dokumen. Sumber wajib inline.""",

    "qualitative": """Anda adalah research assistant sains sosial untuk ResearcherHQ.

Fokus: thematic analysis, coding, grounded theory, phenomenology.
PERATURAN WAJIB: Jawab HANYA dari dokumen. Sumber wajib inline.""",

    "medicine": """Anda adalah research assistant perubatan untuk ResearcherHQ.

Gunakan PICO framework. Rujuk level of evidence dan PRISMA.
PERATURAN WAJIB: Jawab HANYA dari dokumen. Sumber wajib inline.""",
}

OUTPUT_MODE_PROMPTS = {
    "qa": "",
    "literature_review": """
Format output sebagai Literature Review akademik:
1. PENGENALAN — konteks topik
2. SOROTAN KAJIAN — kupasan tema utama dengan citation
3. JURANG KAJIAN — apa yang masih kurang
4. RUMUSAN — sintesis keseluruhan
Gunakan bahasa akademik formal.""",
    "executive_summary": """
Format output sebagai Executive Summary (1-2 muka surat):
- Poin utama kajian
- Metodologi (ringkas)
- Dapatan utama
- Implikasi
Padat dan tepat.""",
    "key_findings": """
Format output sebagai Key Findings berstruktur:
- Bullet point setiap dapatan utama
- Setiap dapatan: DAPATAN → BUKTI (citation) → IMPLIKASI
Jelas dan boleh diambil tindakan.""",
    "research_gap": """
Format output sebagai Research Gap Analysis:
- Rumuskan kajian sedia ada (dari dokumen)
- Kenal pasti jurang dan kekurangan
- Cadang arah kajian hadapan
Berstruktur, akademik.""",
}

KREDIT_COST = {
    "qa": 1,
    "qa_deep": 3,
    "key_findings": 3,
    "executive_summary": 5,
    "literature_review": 10,
    "research_gap": 10,
}

async def query_llm(
    messages: List[Dict],
    research_mode: str = "general",
    output_mode: str = "qa",
    query_type: str = "normal",
) -> Dict:
    system_prompt = SYSTEM_PROMPTS.get(research_mode, SYSTEM_PROMPTS["general"])
    output_prompt = OUTPUT_MODE_PROMPTS.get(output_mode, "")
    if output_prompt:
        system_prompt = system_prompt + "\n\n" + output_prompt

    use_pro = output_mode in ("literature_review", "research_gap") or query_type == "deep"
    model = settings.deepseek_model_pro if use_pro else settings.deepseek_model_flash

    full_messages = [{"role": "system", "content": system_prompt}] + messages

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": full_messages,
                "temperature": 0.1,
                "top_p": 0.1,
                "max_tokens": 4096,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    return {
        "content": data["choices"][0]["message"]["content"],
        "tokens_used": data["usage"]["total_tokens"],
        "model": model,
    }
