import asyncio
import io
import uuid
from typing import Dict

try:
    from docx import Document
    from docx.shared import Pt, Cm
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

# job_id → {"status": "pending"|"done"|"error", "bytes": bytes|None, "filename": str}
_jobs: Dict[str, dict] = {}
_queue: asyncio.Queue = None


def get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def start_export_worker():
    global _queue
    _queue = asyncio.Queue()
    q = _queue
    while True:
        job_id, chapter_title, content = await q.get()
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _build_docx, chapter_title, content
            )
            _jobs[job_id] = {"status": "done", "bytes": result, "filename": f"{chapter_title}.docx"}
        except Exception as e:
            _jobs[job_id] = {"status": "error", "bytes": None, "filename": "", "error": str(e)}
        finally:
            q.task_done()


def _build_docx(chapter_title: str, content: str) -> bytes:
    if not DOCX_AVAILABLE:
        raise RuntimeError("python-docx tidak dipasang.")
    doc = Document()
    doc.add_heading(chapter_title, level=1)
    for para in content.split("\n\n"):
        stripped = para.strip()
        if stripped:
            doc.add_paragraph(stripped)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def enqueue_export(chapter_title: str, content: str) -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "bytes": None, "filename": ""}
    get_queue().put_nowait((job_id, chapter_title, content))
    return job_id


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)
