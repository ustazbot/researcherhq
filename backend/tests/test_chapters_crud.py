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


def test_list_chapters_has_content_false(client_with_chapter):
    """Chapter created fresh has no content → has_content = 0."""
    client, project_id, chapter_id, h = client_with_chapter
    res = client.get(f"/projects/{project_id}/chapters", headers=h)
    assert res.status_code == 200
    chapters = res.json()
    assert len(chapters) == 1
    assert chapters[0]["has_content"] == 0


def test_list_chapters_has_content_true(client_with_chapter):
    """Chapter with saved content → has_content = 1."""
    client, project_id, chapter_id, h = client_with_chapter
    # Write some content
    client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}/content",
        json={"content": "Ini kandungan bab yang cukup panjang untuk dikesan."},
        headers=h
    )
    res = client.get(f"/projects/{project_id}/chapters", headers=h)
    assert res.status_code == 200
    chapters = res.json()
    assert chapters[0]["has_content"] == 1


# --- Task 16: Chapter Content Save + Summary ---

def test_update_chapter_content_saves_and_generates_summary(client_with_chapter, monkeypatch):
    client, project_id, chapter_id, h = client_with_chapter

    async def _mock_llm(messages, **kwargs):
        return {"content": "Ringkasan ujian.", "tokens_used": 10, "model": "mock"}

    monkeypatch.setattr("app.routers.chapters.query_llm", _mock_llm)

    r = client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}/content",
        json={"content": "Kandungan bab yang panjang untuk diringkaskan."},
        headers=h
    )
    assert r.status_code == 200
    assert r.json()["summary_generated"] is True

    import sqlite3, app.database as _db
    conn = sqlite3.connect(_db._db_path)
    row = conn.execute(
        "SELECT content, summary FROM chapter_content WHERE chapter_id=?", (chapter_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "Kandungan bab yang panjang untuk diringkaskan."
    assert row[1] == "Ringkasan ujian."


def test_update_chapter_content_saves_even_if_summary_fails(client_with_chapter, monkeypatch):
    client, project_id, chapter_id, h = client_with_chapter

    async def _fail_llm(*args, **kwargs):
        raise RuntimeError("LLM tidak tersedia")

    monkeypatch.setattr("app.routers.chapters.query_llm", _fail_llm)

    r = client.patch(
        f"/projects/{project_id}/chapters/{chapter_id}/content",
        json={"content": "Kandungan tetap tersimpan walaupun LLM gagal."},
        headers=h
    )
    assert r.status_code == 200

    import sqlite3, app.database as _db
    conn = sqlite3.connect(_db._db_path)
    row = conn.execute(
        "SELECT content, summary FROM chapter_content WHERE chapter_id=?", (chapter_id,)
    ).fetchone()
    conn.close()
    assert row[0] == "Kandungan tetap tersimpan walaupun LLM gagal."
    assert row[1] == ""


# --- Task 19: Bibliography endpoint ---

def test_bibliography_endpoint_returns_deduplicated_sources(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter

    # Create a second chapter
    chap2 = client.post(
        f"/projects/{project_id}/chapters",
        json={"title": "Bab 2: Metodologi", "chapter_order": 2},
        headers=h
    ).json()
    chapter_id2 = chap2["id"]

    import sqlite3, json as _json, app.database as _db
    conn = sqlite3.connect(_db._db_path)

    shared = {"filename": "artikel_sama.pdf", "page_number": 5}
    unique1 = {"filename": "unik_bab1.pdf", "page_number": 1}
    unique2 = {"filename": "unik_bab2.pdf", "page_number": 3}

    conn.execute(
        "UPDATE chapter_content SET source_citations=? WHERE chapter_id=?",
        (_json.dumps([shared, unique1]), chapter_id)
    )
    conn.execute(
        "UPDATE chapter_content SET source_citations=? WHERE chapter_id=?",
        (_json.dumps([shared, unique2]), chapter_id2)
    )
    conn.commit()
    conn.close()

    r = client.get(f"/projects/{project_id}/bibliography", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["citation_style"] == "APA7"

    sources = {(s["filename"], s["page_number"]): s for s in data["sources"]}
    assert len(sources) == 3  # shared deduplicated, 2 unique

    shared_entry = sources[("artikel_sama.pdf", 5)]
    assert len(shared_entry["chapter_titles"]) == 2
    assert "Bab 1: Pengenalan" in shared_entry["chapter_titles"]
    assert "Bab 2: Metodologi" in shared_entry["chapter_titles"]


def test_bibliography_empty_project(client_with_chapter):
    client, project_id, _, h = client_with_chapter
    r = client.get(f"/projects/{project_id}/bibliography", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["sources"] == []

# --- §6J: word_count_target ---

def _get_target_in_db(client, project_id, chapter_id, h):
    """Read the persisted target via the list endpoint (ch.* includes it)."""
    rows = client.get(f"/projects/{project_id}/chapters", headers=h).json()
    return next(r for r in rows if r["id"] == chapter_id)["word_count_target"]

def test_create_chapter_with_word_target(client_with_chapter):
    client, project_id, _, h = client_with_chapter
    r = client.post(f"/projects/{project_id}/chapters",
                    json={"title": "Bab 2", "chapter_order": 2, "word_count_target": 5000}, headers=h)
    assert r.status_code == 201
    assert r.json()["word_count_target"] == 5000
    assert _get_target_in_db(client, project_id, r.json()["id"], h) == 5000

def test_create_chapter_without_word_target_null(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    # fixture chapter was created without a target
    assert _get_target_in_db(client, project_id, chapter_id, h) is None

def test_update_set_target_from_null(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                     json={"word_count_target": 3000}, headers=h)
    assert r.status_code == 200
    assert r.json()["word_count_target"] == 3000
    assert _get_target_in_db(client, project_id, chapter_id, h) == 3000

def test_update_change_existing_target(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                 json={"word_count_target": 3000}, headers=h)
    r = client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                     json={"word_count_target": 8000}, headers=h)
    assert r.json()["word_count_target"] == 8000
    assert _get_target_in_db(client, project_id, chapter_id, h) == 8000

def test_update_none_keeps_existing_target(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                 json={"word_count_target": 4000}, headers=h)
    # a PATCH that only renames must not touch the target (None = unchanged)
    r = client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                     json={"title": "Bab 1 (edited)"}, headers=h)
    assert r.status_code == 200
    assert r.json()["word_count_target"] == 4000
    assert _get_target_in_db(client, project_id, chapter_id, h) == 4000

def test_update_zero_sentinel_clears_target(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                 json={"word_count_target": 4000}, headers=h)
    r = client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                     json={"word_count_target": 0}, headers=h)
    assert r.status_code == 200
    assert r.json()["word_count_target"] is None
    assert _get_target_in_db(client, project_id, chapter_id, h) is None

def test_negative_target_422(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    r = client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                     json={"word_count_target": -100}, headers=h)
    assert r.status_code == 422
    r2 = client.post(f"/projects/{project_id}/chapters",
                     json={"title": "Bab X", "chapter_order": 9, "word_count_target": -1}, headers=h)
    assert r2.status_code == 422

def test_list_chapters_includes_target_and_nulls(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    client.post(f"/projects/{project_id}/chapters",
                json={"title": "Bab 2", "chapter_order": 2, "word_count_target": 6000}, headers=h)
    rows = client.get(f"/projects/{project_id}/chapters", headers=h).json()
    by_title = {r["title"]: r for r in rows}
    assert by_title["Bab 1: Pengenalan"]["word_count_target"] is None
    assert by_title["Bab 2"]["word_count_target"] == 6000
    # §6J: list also carries content so the client can count words locally
    assert all("content" in r for r in rows)

def test_get_single_chapter_includes_target(client_with_chapter):
    client, project_id, chapter_id, h = client_with_chapter
    client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                 json={"word_count_target": 2500}, headers=h)
    r = client.get(f"/projects/{project_id}/chapters/{chapter_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["word_count_target"] == 2500

def test_target_ownership_other_user_404(client_with_chapter):
    client, project_id, chapter_id, _ = client_with_chapter
    other = make_headers(user_id="user-2", email="u2@test.com")
    r = client.patch(f"/projects/{project_id}/chapters/{chapter_id}",
                     json={"word_count_target": 1000}, headers=other)
    assert r.status_code == 404
