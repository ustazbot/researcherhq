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
