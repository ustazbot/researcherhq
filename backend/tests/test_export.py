import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import asyncio
import pytest
import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt


def make_headers(user_id="user-exp", email="exp@test.com"):
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client_with_user(tmp_path):
    db_path = str(tmp_path / "export_test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            proj_resp = c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)
            proj_id = proj_resp.json()["id"]
            yield c, headers, proj_id


def test_enqueue_creates_pending_job():
    from app.services.export_service import enqueue_export, get_job
    job_id = enqueue_export("Bab 1", "Kandungan bab pertama.")
    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "pending"


def test_get_job_unknown_returns_none():
    from app.services.export_service import get_job
    assert get_job(str(uuid.uuid4())) is None


def test_build_docx_returns_bytes():
    from app.services.export_service import _build_docx
    try:
        result = _build_docx("Bab Ujian", "Perenggan pertama.\n\nPerenggan kedua.")
        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[:2] == b"PK"
    except RuntimeError as e:
        if "python-docx" in str(e):
            pytest.skip("python-docx tidak dipasang")
        raise


def test_export_worker_processes_job():
    from app.services import export_service

    async def _run():
        # start_export_worker creates a fresh queue; enqueue after it starts
        worker = asyncio.create_task(export_service.start_export_worker())
        await asyncio.sleep(0)  # let worker initialize queue
        job_id = export_service.enqueue_export("Bab Dua", "Kandungan bab dua.\n\nTamat.")
        await export_service.get_queue().join()
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
        return job_id

    job_id = asyncio.run(_run())
    # Reset queue so subsequent TestClient tests get a fresh queue
    export_service._queue = None

    job = export_service.get_job(job_id)
    if job["status"] == "error" and "python-docx" in job.get("error", ""):
        pytest.skip("python-docx tidak dipasang")

    assert job["status"] == "done"
    assert isinstance(job["bytes"], bytes)
    assert job["filename"].endswith(".docx")


def test_export_endpoint_requires_pro(client_with_user):
    client, headers, proj_id = client_with_user
    chap_resp = client.post(
        f"/projects/{proj_id}/chapters",
        json={"title": "Bab 1", "chapter_order": 1},
        headers=headers
    )
    assert chap_resp.status_code == 201, chap_resp.text
    chap = chap_resp.json()
    resp = client.post(
        f"/projects/{proj_id}/chapters/{chap['id']}/export",
        headers=headers
    )
    assert resp.status_code == 403
    assert "Pro" in resp.json()["detail"]


def test_poll_export_unknown_job(client_with_user):
    client, headers, proj_id = client_with_user
    fake_chap = str(uuid.uuid4())
    fake_job = str(uuid.uuid4())
    resp = client.get(
        f"/projects/{proj_id}/chapters/{fake_chap}/export/{fake_job}",
        headers=headers
    )
    assert resp.status_code == 404


# --- Task 20: thesis compile ---

def test_build_thesis_docx_returns_valid_docx():
    from app.services.export_service import _build_thesis_docx
    try:
        chapters = [
            {"title": "Pendahuluan", "content": "Ini bab pertama.\n\nPerenggan dua.", "section_type": "front_matter", "chapter_order": 0},
            {"title": "Bab 1: Kajian", "content": "Kandungan kajian di sini.", "section_type": "chapter", "chapter_order": 1},
        ]
        bibliography = [{"filename": "artikel.pdf", "page_number": 5}]
        result = _build_thesis_docx("Tesis Ujian", chapters, bibliography, "APA7")
        assert isinstance(result, bytes)
        assert len(result) > 0
        assert result[:2] == b"PK"  # valid ZIP/docx
    except RuntimeError as e:
        if "python-docx" in str(e):
            pytest.skip("python-docx tidak dipasang")
        raise


def test_enqueue_thesis_compile_creates_pending_job():
    from app.services.export_service import enqueue_thesis_compile, get_job
    job_id = enqueue_thesis_compile(
        project_title="Projek Ujian",
        chapters=[{"title": "Bab 1", "content": "Kandungan.", "section_type": "chapter", "chapter_order": 1}],
        bibliography=[],
        citation_style="APA7",
    )
    job = get_job(job_id)
    assert job is not None
    assert job["status"] == "pending"


def test_compile_endpoint_requires_pro(client_with_user):
    client, headers, proj_id = client_with_user
    resp = client.post(f"/projects/{proj_id}/compile", headers=headers)
    assert resp.status_code == 403
    assert "Pro" in resp.json()["detail"]


def test_compile_endpoint_requires_chapters(client_with_user):
    import sqlite3
    from unittest.mock import patch as _patch
    import app.database as _db

    client, headers, proj_id = client_with_user
    # Upgrade user to pro
    conn = sqlite3.connect(_db._db_path)
    conn.execute("UPDATE users SET tier='pro' WHERE id='user-exp'")
    conn.commit()
    conn.close()

    resp = client.post(f"/projects/{proj_id}/compile", headers=headers)
    assert resp.status_code == 400
    assert "bab" in resp.json()["detail"].lower()


def test_poll_compile_unknown_job(client_with_user):
    client, headers, proj_id = client_with_user
    fake_job = str(uuid.uuid4())
    resp = client.get(f"/projects/{proj_id}/compile/{fake_job}", headers=headers)
    assert resp.status_code == 404


def test_compile_endpoint_all_chapters_empty(client_with_user):
    import sqlite3
    import app.database as _db

    client, headers, proj_id = client_with_user
    # Upgrade to pro
    conn = sqlite3.connect(_db._db_path)
    conn.execute("UPDATE users SET tier='pro' WHERE id='user-exp'")
    conn.commit()
    conn.close()

    # Add chapter with NO content (stays empty)
    chap_resp = client.post(
        f"/projects/{proj_id}/chapters",
        json={"title": "Bab Kosong", "chapter_order": 1},
        headers=headers
    )
    assert chap_resp.status_code == 201

    resp = client.post(f"/projects/{proj_id}/compile", headers=headers)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "all_chapters_empty"
    assert "Bab Kosong" in detail["empty_chapters"]
