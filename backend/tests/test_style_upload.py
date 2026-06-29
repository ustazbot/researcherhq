import io
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
import uuid
from datetime import datetime, date
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.database import init_db
from app.services.auth_service import create_jwt


def make_token(user_id=None, email=None):
    uid = user_id or str(uuid.uuid4())
    em = email or f"test_{uuid.uuid4().hex[:6]}@test.com"
    return create_jwt({"user_id": uid, "email": em}), uid, em


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            yield c, db_path


def _reset_date():
    today = date.today()
    if today.month == 12:
        return date(today.year + 1, 1, 1).isoformat()
    return date(today.year, today.month + 1, 1).isoformat()


def _seed_user(db_path, user_id, email, tier="pro"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO users
           (id, email, tier, kredit_remaining, kredit_total, tokens_used_internal, reset_date, created_at)
           VALUES (?, ?, ?, 50, 50, 0, ?, ?)""",
        (user_id, email, tier, _reset_date(), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def _seed_project(db_path, project_id, user_id):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT INTO projects (id, user_id, title, research_mode, created_at)
           VALUES (?, ?, 'Test Project', 'general', ?)""",
        (project_id, user_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def _make_docx_bytes(text: str) -> bytes:
    """Create a minimal valid .docx with the given text."""
    import docx
    doc = docx.Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _upload(c, pid, token, file_bytes, filename, content_type):
    return c.post(
        f"/voice-profile/{pid}/analyse-sample",
        files={"file": (filename, io.BytesIO(file_bytes), content_type)},
        headers={"Authorization": f"Bearer {token}"},
    )


MOCK_ANALYSIS = "This author tends to use concise, direct sentences with active voice."


@patch("app.services.llm_provider.call_deepseek_raw", new_callable=AsyncMock, return_value=MOCK_ANALYSIS)
def test_valid_docx_upload(mock_llm, client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    text = "This is a sample paragraph. " * 20  # enough words
    file_bytes = _make_docx_bytes(text)
    r = _upload(c, pid, token, file_bytes, "sample.docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert r.status_code == 200
    data = r.json()
    assert "style_description" in data
    assert data["style_description"] == MOCK_ANALYSIS.strip()


@patch("app.services.llm_provider.call_deepseek_raw", new_callable=AsyncMock, return_value=MOCK_ANALYSIS)
def test_valid_txt_upload(mock_llm, client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    text = ("This is a well-written sentence. " * 30).encode("utf-8")
    r = _upload(c, pid, token, text, "sample.txt", "text/plain")
    assert r.status_code == 200
    assert r.json()["style_description"] == MOCK_ANALYSIS.strip()


def test_invalid_file_type_pdf(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = _upload(c, pid, token, b"%PDF-1.4 fake pdf", "sample.pdf", "application/pdf")
    assert r.status_code == 400


def test_empty_file(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = _upload(c, pid, token, b"", "sample.txt", "text/plain")
    assert r.status_code == 422


def test_text_too_short(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = _upload(c, pid, token, b"Short text.", "sample.txt", "text/plain")
    assert r.status_code == 422


def test_file_too_large(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    big = b"x" * (5 * 1024 * 1024 + 1)
    r = _upload(c, pid, token, big, "sample.txt", "text/plain")
    assert r.status_code == 413


def test_free_tier_rejected(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="free")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = _upload(c, pid, token, b"hello world", "sample.txt", "text/plain")
    assert r.status_code == 403


def test_wrong_project_rejected(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    # don't seed a project owned by this user
    other_pid = str(uuid.uuid4())
    other_token, other_uid, other_email = make_token()
    _seed_user(db_path, other_uid, other_email, tier="pro")
    _seed_project(db_path, other_pid, other_uid)

    r = _upload(c, other_pid, token, b"sample text content here.", "sample.txt", "text/plain")
    assert r.status_code == 403


def test_sample_analysis_saved_and_in_style_notes(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    analysis = "This author tends to use complex sentences."
    r = c.post(
        f"/voice-profile/{pid}",
        json={"answers": {"q1": "Panjang"}, "sample_analysis": analysis},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["sample_analysis"] == analysis
    assert "Analisis gaya tulisan" in data["style_notes"]
    assert analysis[:50] in data["style_notes"]


def test_get_returns_sample_analysis(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    analysis = "This author tends to favour passive constructions."
    c.post(
        f"/voice-profile/{pid}",
        json={"answers": {"q1": "Panjang"}, "sample_analysis": analysis},
        headers={"Authorization": f"Bearer {token}"},
    )

    r = c.get(f"/voice-profile/{pid}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["sample_analysis"] == analysis
