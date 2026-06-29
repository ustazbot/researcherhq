import io
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter()


def _verify_project(project_id: str, user_id: str, db):
    row = db.execute(
        "SELECT id FROM projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    ).fetchone()
    if not row:
        raise HTTPException(403, "Projek tidak dijumpai atau akses ditolak.")
    return row


def build_style_notes(answers: dict, sample_excerpt: str = None, sample_analysis: str = None) -> str:
    lines = ["GAYA PENULISAN USER (ikut keutamaan ini):"]
    q_labels = {
        "q1": "Panjang ayat",
        "q2": "Gaya penulisan",
        "q3": "Keutamaan lain",
    }
    for key, label in q_labels.items():
        if answers.get(key):
            lines.append(f"- {label}: {answers[key]}")
    if sample_analysis:
        lines.append(f"- Analisis gaya tulisan (daripada sampel): {sample_analysis[:400]}")
    elif sample_excerpt:
        excerpt = sample_excerpt[:300].strip()
        lines.append(f'- Contoh gaya tulisan user: "{excerpt}"')
    return "\n".join(lines)


@router.get("/{project_id}")
def get_voice_profile(project_id: str, user=Depends(get_current_user)):
    with get_db() as db:
        _verify_project(project_id, user["user_id"], db)
        row = db.execute(
            "SELECT style_notes, sample_excerpt, sample_analysis, updated_at FROM voice_profile WHERE project_id = ?",
            (project_id,),
        ).fetchone()
    if not row:
        return {"exists": False}
    return {
        "exists": True,
        "style_notes": row["style_notes"],
        "sample_excerpt": row["sample_excerpt"],
        "sample_analysis": row["sample_analysis"],
        "updated_at": row["updated_at"],
    }


MAX_SAMPLE_SIZE = 5 * 1024 * 1024  # 5MB

ALLOWED_SAMPLE_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
}

STYLE_ANALYSIS_PROMPT = """You are a writing style analyst. Analyse the academic writing sample below and produce a concise structured description of the author's writing style.

Focus ONLY on these dimensions:
- Sentence length and structure (short/long/mixed, simple/complex syntax)
- Voice (active vs passive preference)
- Formality level (formal academic / semi-formal / informal)
- Vocabulary patterns (field-specific jargon, hedging language, transition words used)
- Any distinctive stylistic habits (repetition, specific phrases, paragraph length)

Output format — plain text, 100–150 words, no headings, no bullet points. Write as if completing this sentence: "This author tends to..."

Do NOT comment on the content or topic of the writing. Style only.

Writing sample:
{sample_text}"""


@router.post("/{project_id}/analyse-sample")
async def analyse_writing_sample(
    project_id: str,
    file: UploadFile = File(...),
    user=Depends(get_current_user),
):
    # 1. Pro gate
    with get_db() as db:
        _verify_project(project_id, user["user_id"], db)
        user_row = db.execute(
            "SELECT tier FROM users WHERE id = ?", (user["user_id"],)
        ).fetchone()
        if not user_row or user_row["tier"] != "pro":
            raise HTTPException(403, "Writing sample upload is a Pro feature.")

    # 2. Validate file type
    if file.content_type not in ALLOWED_SAMPLE_TYPES:
        raise HTTPException(400, "Only .docx and .txt files are supported.")

    file_type = ALLOWED_SAMPLE_TYPES[file.content_type]

    # 3. Read bytes — in-memory only
    file_bytes = await file.read()
    if len(file_bytes) > MAX_SAMPLE_SIZE:
        raise HTTPException(413, "File too large. Maximum size is 5MB.")
    if not file_bytes:
        raise HTTPException(422, "File is empty.")

    # 4. Extract text
    try:
        if file_type == "docx":
            import docx
            doc = docx.Document(io.BytesIO(file_bytes))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            sample_text = "\n\n".join(paragraphs)
        else:  # txt
            sample_text = file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        raise HTTPException(422, "Could not read file. Please check it is not corrupted or password-protected.")

    # 5. Discard file bytes immediately
    del file_bytes

    # 6. Truncate to 3000 words
    words = sample_text.split()
    if len(words) > 3000:
        sample_text = " ".join(words[:3000])

    if len(sample_text.strip()) < 50:
        raise HTTPException(422, "Not enough text found in file. Please upload a file with at least a few paragraphs.")

    # 7. Call LLM for style analysis
    from app.services.llm_provider import call_deepseek_raw

    prompt = STYLE_ANALYSIS_PROMPT.format(sample_text=sample_text)
    try:
        style_description = await call_deepseek_raw(prompt, max_tokens=300)
    except Exception:
        raise HTTPException(503, "Style analysis failed. Please try again.")

    return {
        "style_description": style_description.strip(),
        "word_count": len(words),
    }


class VoiceProfileBody(BaseModel):
    answers: dict
    sample_excerpt: Optional[str] = None
    sample_analysis: Optional[str] = None


@router.post("/{project_id}")
def save_voice_profile(
    project_id: str,
    body: VoiceProfileBody,
    user=Depends(get_current_user),
):
    with get_db() as db:
        _verify_project(project_id, user["user_id"], db)

        user_row = db.execute(
            "SELECT tier FROM users WHERE id = ?", (user["user_id"],)
        ).fetchone()
        if not user_row or user_row["tier"] != "pro":
            raise HTTPException(403, "Profil Gaya Penulisan hanya tersedia untuk pengguna Pro.")

        excerpt = body.sample_excerpt[:500].strip() if body.sample_excerpt else None
        analysis = body.sample_analysis[:2000].strip() if body.sample_analysis else None
        style_notes = build_style_notes(body.answers, excerpt, analysis)
        now = datetime.utcnow().isoformat()

        existing = db.execute(
            "SELECT id FROM voice_profile WHERE project_id = ?", (project_id,)
        ).fetchone()

        if existing:
            db.execute(
                """UPDATE voice_profile
                   SET style_notes = ?, sample_excerpt = ?, sample_analysis = ?, updated_at = ?
                   WHERE project_id = ?""",
                (style_notes, excerpt, analysis, now, project_id),
            )
            row_id = existing["id"]
        else:
            row_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO voice_profile
                   (id, project_id, style_notes, sample_excerpt, sample_analysis, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (row_id, project_id, style_notes, excerpt, analysis, now, now),
            )

    return {
        "exists": True,
        "style_notes": style_notes,
        "sample_excerpt": excerpt,
        "sample_analysis": analysis,
        "updated_at": now,
    }
