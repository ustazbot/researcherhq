import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
import uuid
from datetime import datetime, date
from unittest.mock import patch, AsyncMock, MagicMock
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


# ── Fake API results ────────────────────────────────────────────────────────

FAKE_OPENALEX = [
    {"source": "openalex", "title": "Financial Literacy Study", "authors": ["Ahmad Ali"], "year": 2022,
     "journal": "Journal A", "doi": "10.1234/fin1", "abstract": "Abstract A", "cited_by": 50, "url": ""},
]
FAKE_SS = [
    {"source": "semantic_scholar", "title": "Kesedaran Kewangan IPTA", "authors": ["Lee Chen"], "year": 2021,
     "journal": "Journal B", "doi": "10.1234/fin2", "abstract": "Abstract B", "cited_by": 30, "url": ""},
]
FAKE_CROSSREF = [
    {"source": "crossref", "title": "Islamic Finance Review", "authors": ["Siti Noor"], "year": 2020,
     "journal": "Journal C", "doi": "10.1234/fin3", "abstract": "Abstract C", "cited_by": 0, "url": ""},
]
FAKE_DUPLICATE = [
    # Same DOI as FAKE_OPENALEX — should be deduped
    {"source": "semantic_scholar", "title": "Financial Literacy Study", "authors": ["Ahmad Ali"], "year": 2022,
     "journal": "Journal A", "doi": "10.1234/fin1", "abstract": "Abstract A", "cited_by": 50, "url": ""},
]


def _mock_search_fns(oa=None, ss=None, cr=None):
    """Patch the three search functions to return predetermined results."""
    oa_result = oa if oa is not None else FAKE_OPENALEX
    ss_result = ss if ss is not None else FAKE_SS
    cr_result = cr if cr is not None else FAKE_CROSSREF

    async def fake_oa(*a, **kw): return oa_result
    async def fake_ss(*a, **kw): return ss_result
    async def fake_cr(*a, **kw): return cr_result

    return (
        patch("app.routers.search.search_openalex", side_effect=fake_oa),
        patch("app.routers.search.search_semantic_scholar", side_effect=fake_ss),
        patch("app.routers.search.search_crossref", side_effect=fake_cr),
    )


# ── Tests ───────────────────────────────────────────────────────────────────

def test_search_articles_requires_auth(client):
    c, _ = client
    r = c.get("/search/articles?q=finance&project_id=x")
    assert r.status_code == 401  # no auth header → JWT middleware rejects


def test_search_articles_wrong_project(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email)
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    # Different user's token trying to access this project
    token2, uid2, email2 = make_token()
    _seed_user(db_path, uid2, email2)

    p1, p2, p3 = _mock_search_fns()
    with p1, p2, p3:
        r = c.get(f"/search/articles?q=finance&project_id={pid}",
                  headers={"Authorization": f"Bearer {token2}"})
    assert r.status_code == 403


def test_search_articles_short_query(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email)
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    r = c.get(f"/search/articles?q=ab&project_id={pid}",
              headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 400


def test_search_articles_returns_merged_results(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    p1, p2, p3 = _mock_search_fns()
    with p1, p2, p3:
        r = c.get(f"/search/articles?q=finance&project_id={pid}",
                  headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 3
    sources = {a["source"] for a in data["results"]}
    assert "openalex" in sources
    assert "semantic_scholar" in sources
    assert "crossref" in sources


def test_search_articles_deduplicates_doi(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    # OpenAlex and SS both return same DOI
    p1, p2, p3 = _mock_search_fns(oa=FAKE_OPENALEX, ss=FAKE_DUPLICATE, cr=[])
    with p1, p2, p3:
        r = c.get(f"/search/articles?q=finance&project_id={pid}",
                  headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    dois = [a["doi"] for a in r.json()["results"]]
    assert dois.count("10.1234/fin1") == 1


def test_search_articles_free_tier_limited(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="free")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    # Return 10 results total
    many = [{"source": "openalex", "title": f"Paper {i}", "authors": ["A"], "year": 2020,
              "journal": "J", "doi": f"10.1/{i}", "abstract": "abs", "cited_by": i, "url": ""}
             for i in range(10)]
    p1, p2, p3 = _mock_search_fns(oa=many, ss=[], cr=[])
    with p1, p2, p3:
        r = c.get(f"/search/articles?q=finance&project_id={pid}",
                  headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 5


def test_accept_article_creates_document(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    long_abstract = " ".join(["This study examines financial literacy among Malaysian university students."] * 10)
    r = c.post("/search/accept", json={
        "project_id": pid,
        "title": "Test Article",
        "authors": ["Ahmad Ali", "Lee Chen"],
        "year": 2023,
        "journal": "Journal X",
        "doi": "10.9999/test1",
        "abstract": long_abstract,
        "url": "https://doi.org/10.9999/test1",
        "source": "openalex",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    data = r.json()
    assert data["filename"].startswith("Ali")
    assert data["chunk_count"] > 0

    # Verify in DB
    conn = sqlite3.connect(db_path)
    doc = conn.execute("SELECT * FROM documents WHERE project_id = ?", (pid,)).fetchone()
    conn.close()
    assert doc is not None


def test_accept_article_duplicate_doi_rejected(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "project_id": pid,
        "title": "Test Article",
        "authors": ["Ahmad Ali"],
        "year": 2023,
        "journal": "Journal X",
        "doi": "10.9999/dup123",
        "abstract": "Abstract here.",
        "url": "",
        "source": "openalex",
    }
    c.post("/search/accept", json=payload, headers=headers)
    r2 = c.post("/search/accept", json=payload, headers=headers)
    assert r2.status_code == 409


def test_accept_article_free_tier_limit(client):
    """Free users now get 403 at the Pro gate, before doc count check."""
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="free")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = c.post("/search/accept", json={
        "project_id": pid,
        "title": "Second Article",
        "authors": ["B"],
        "year": 2020,
        "journal": "J",
        "doi": "10.1/x",
        "abstract": "abs",
        "url": "",
        "source": "crossref",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


# ── 32A: Schema columns ────────────────────────────────────────────────────────

def test_documents_has_source_type_column(client):
    _, db_path = client
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    conn.close()
    assert "source_type" in cols


def test_documents_has_content_level_column(client):
    _, db_path = client
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    conn.close()
    assert "content_level" in cols


def test_documents_has_openalex_id_column(client):
    _, db_path = client
    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
    conn.close()
    assert "openalex_id" in cols


# ── 32B: Pro gate accept ───────────────────────────────────────────────────────

def test_accept_article_free_user_forbidden(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="free")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = c.post("/search/accept", json={
        "project_id": pid,
        "title": "Some Article",
        "authors": ["X"],
        "year": 2022,
        "journal": "J",
        "doi": "10.x/free",
        "abstract": "abstract here",
        "url": "",
        "source": "openalex",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403
    assert "Pro" in r.json()["detail"]


# ── 32B: columns stored on accept ─────────────────────────────────────────────

def _accept_payload(pid, doi="10.x/col1", is_oa=False, oa_url=None, openalex_id=None):
    return {
        "project_id": pid,
        "title": "Column Test Article",
        "authors": ["Tester"],
        "year": 2023,
        "journal": "Journal T",
        "doi": doi,
        "abstract": "This is a test abstract for column verification purposes.",
        "url": "",
        "source": "openalex",
        "is_oa": is_oa,
        "oa_url": oa_url,
        "openalex_id": openalex_id,
        "cited_by": 5,
    }


def test_accept_article_stores_source_type(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = c.post("/search/accept", json=_accept_payload(pid, doi="10.x/st1"),
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    doc = conn.execute("SELECT * FROM documents WHERE project_id = ?", (pid,)).fetchone()
    conn.close()
    assert doc["source_type"] == "search_result"


def test_accept_article_stores_content_level_abstract(client):
    """Non-OA article → content_level = abstract_only."""
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = c.post("/search/accept", json=_accept_payload(pid, doi="10.x/cl1", is_oa=False),
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    assert r.json()["content_level"] == "abstract_only"

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    doc = conn.execute("SELECT content_level FROM documents WHERE project_id = ?", (pid,)).fetchone()
    conn.close()
    assert doc["content_level"] == "abstract_only"


def test_accept_article_stores_openalex_id(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = c.post("/search/accept",
               json=_accept_payload(pid, doi="10.x/oa1", openalex_id="W12345678"),
               headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    doc = conn.execute("SELECT openalex_id FROM documents WHERE project_id = ?", (pid,)).fetchone()
    conn.close()
    assert doc["openalex_id"] == "W12345678"


# ── 32B: duplicate check endpoint ─────────────────────────────────────────────

def test_check_duplicate_no_match(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    r = c.get(f"/search/check-duplicate?project_id={pid}&doi=10.x/nonexistent",
              headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["exists"] is False


def test_check_duplicate_doi_match(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    headers = {"Authorization": f"Bearer {token}"}

    # Accept article first
    c.post("/search/accept", json=_accept_payload(pid, doi="10.x/dup99"),
           headers=headers)

    r = c.get(f"/search/check-duplicate?project_id={pid}&doi=10.x/dup99",
              headers=headers)
    assert r.status_code == 200
    assert r.json()["exists"] is True


def test_check_duplicate_wrong_project(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    token2, uid2, email2 = make_token()
    _seed_user(db_path, uid2, email2, tier="pro")

    r = c.get(f"/search/check-duplicate?project_id={pid}&doi=10.x/x",
              headers={"Authorization": f"Bearer {token2}"})
    assert r.status_code == 403


# ── 32B: is_oa in search results ──────────────────────────────────────────────

def test_search_results_include_is_oa_field(client):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier="pro")
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)

    fake_with_oa = [{
        "source": "openalex", "title": "OA Paper", "authors": ["A"], "year": 2023,
        "journal": "J", "doi": "10.x/oa", "abstract": "abs", "cited_by": 10,
        "url": "", "is_oa": True, "oa_url": "https://example.com/paper.pdf",
        "openalex_id": "W99999",
    }]

    async def fake_oa(*a, **kw): return fake_with_oa
    async def fake_ss(*a, **kw): return []
    async def fake_cr(*a, **kw): return []

    with patch("app.routers.search.search_openalex", side_effect=fake_oa), \
         patch("app.routers.search.search_semantic_scholar", side_effect=fake_ss), \
         patch("app.routers.search.search_crossref", side_effect=fake_cr):
        r = c.get(f"/search/articles?q=oa+paper&project_id={pid}",
                  headers={"Authorization": f"Bearer {token}"})

    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert "is_oa" in results[0]
    assert results[0]["is_oa"] is True
    assert results[0]["oa_url"] == "https://example.com/paper.pdf"
