import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import patch
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt

def make_headers(user_id="user-1", email="u1@test.com"):
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def client_with_chapter(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            h = make_headers()
            proj_r = c.post("/projects", json={"title": "Tesis", "research_mode": "general"}, headers=h)
            project_id = proj_r.json()["id"]
            chap_r = c.post(
                f"/projects/{project_id}/chapters",
                json={"title": "Bab 1: Pengenalan", "chapter_order": 1},
                headers=h
            )
            chapter_id = chap_r.json()["id"]
            yield c, project_id, chapter_id, h

# --- GET single chapter ---

def test_get_chapter_returns_content(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.get(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == chapter_id
    assert data["title"] == "Bab 1: Pengenalan"
    assert "content" in data
    assert data["content"] == ""  # fresh chapter starts empty

def test_get_chapter_not_found(client_with_chapter):
    client, project_id, _, h = client_with_chapter
    r = client.get(f"/projects/{project_id}/chapters/nonexistent", headers=h)
    assert r.status_code == 404

# --- DELETE chapter ---

def test_delete_chapter(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.delete(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)
    assert r.status_code == 204
    # Verify chapter gone
    r2 = client.get(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)
    assert r2.status_code == 404

def test_delete_chapter_cascades_content(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    import sqlite3, app.database as _db
    conn = sqlite3.connect(_db._db_path)
    before = conn.execute("SELECT id FROM chapter_content WHERE chapter_id=?", (chapter_id,)).fetchone()
    conn.close()
    assert before is not None  # content row exists

    client.delete(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)

    conn2 = sqlite3.connect(_db._db_path)
    after = conn2.execute("SELECT id FROM chapter_content WHERE chapter_id=?", (chapter_id,)).fetchone()
    conn2.close()
    assert after is None  # cascaded

def test_delete_chapter_wrong_user(client_with_chapter):
    client, project_id, chapter_id, _ = client_with_chapter
    other_h = make_headers("user-2", "u2@test.com")
    r = client.delete(f"/projects/{project_id}/chapters/{chapter_id}", headers=other_h)
    assert r.status_code == 404  # project not found for other user

# --- PATCH chapter meta ---

def test_patch_chapter_title(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}",
        json={"title": "Bab 1: Latar Belakang Kajian"},
        headers=h
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Bab 1: Latar Belakang Kajian"

def test_patch_chapter_order(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}",
        json={"chapter_order": 3},
        headers=h
    )
    assert r.status_code == 200
    assert r.json()["chapter_order"] == 3

def test_patch_chapter_partial(client_with_chapter):
    """Patch without title should preserve existing title."""
    client, project_id, chapter_id, h = client_with_chapter
    r = client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}",
        json={"chapter_order": 2},
        headers=h
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Bab 1: Pengenalan"  # preserved

# --- DELETE document ---

@pytest.fixture
def client_with_doc(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            h = make_headers()
            proj_r = c.post("/projects", json={"title": "Tesis", "research_mode": "general"}, headers=h)
            project_id = proj_r.json()["id"]
            doc_r = c.post("/documents/upload", json={
                "project_id": project_id,
                "filename": "artikel.pdf",
                "category": "artikel",
                "pages": [{"page_number": 1, "text": " ".join(["perkataan"] * 150)}]
            }, headers=h)
            doc_id = doc_r.json()["id"]
            yield c, project_id, doc_id, h

def test_delete_document(client_with_doc):
    client, project_id, doc_id, h = client_with_doc
    r = client.delete(f"/documents/{doc_id}", headers=h)
    assert r.status_code == 204
    # Verify doc gone from list
    docs = client.get(f"/documents?project_id={project_id}", headers=h).json()
    assert all(d["id"] != doc_id for d in docs)

def test_delete_document_bumps_version(client_with_doc):
    client, project_id, doc_id, h = client_with_doc
    version_before = client.get(f"/projects/{project_id}", headers=h).json()["document_set_version"]
    client.delete(f"/documents/{doc_id}", headers=h)
    version_after = client.get(f"/projects/{project_id}", headers=h).json()["document_set_version"]
    assert version_after == version_before + 1

def test_delete_document_wrong_user(client_with_doc):
    client, _, doc_id, _ = client_with_doc
    other_h = make_headers("user-2", "u2@test.com")
    r = client.delete(f"/documents/{doc_id}", headers=other_h)
    assert r.status_code == 404
