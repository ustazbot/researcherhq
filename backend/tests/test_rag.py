import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.rag_pipeline import chunk_text

def test_chunk_basic():
    # 500 words should produce multiple chunks
    text = " ".join(["word"] * 500)
    chunks = chunk_text(text)
    assert len(chunks) > 1
    for c in chunks:
        word_count = len(c["text"].split())
        assert word_count <= 420, f"Chunk too large: {word_count} words"

def test_chunk_overlap():
    # With 200 words and overlap 80, should get at least 1 chunk
    text = " ".join([str(i) for i in range(200)])
    chunks = chunk_text(text)
    assert len(chunks) >= 1

def test_chunk_min_size():
    # Chunks smaller than MIN_CHUNK_SIZE should be dropped
    # Short header + 500 words of content
    header = "Tajuk"  # only 1 word — too short for a standalone chunk
    body = " ".join(["word"] * 500)
    text = header + "\n\n" + body
    chunks = chunk_text(text)
    # All chunks should have at least MIN_CHUNK_SIZE words
    for c in chunks:
        assert len(c["text"].split()) >= 10

def test_chunk_has_required_fields():
    text = " ".join(["word"] * 200)
    chunks = chunk_text(text, page_number=3)
    assert len(chunks) >= 1
    c = chunks[0]
    assert "text" in c
    assert "page_number" in c
    assert "chunk_index" in c
    assert c["page_number"] == 3
    assert c["chunk_index"] == 0


from unittest.mock import patch
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt

def make_headers(user_id="user-1", email="u1@test.com"):
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}

import pytest

@pytest.fixture
def client_with_project(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            # Create user + project
            proj_r = c.post("/projects", json={"title": "Test", "research_mode": "general"}, headers=headers)
            project_id = proj_r.json()["id"]
            yield c, project_id, headers

def test_upload_document(client_with_project):
    client, project_id, headers = client_with_project
    r = client.post("/documents/upload", json={
        "project_id": project_id,
        "filename": "test.pdf",
        "category": "artikel",
        "pages": [
            {"page_number": 1, "text": " ".join(["word"] * 150)},
            {"page_number": 2, "text": " ".join(["word"] * 150)},
        ]
    }, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert data["chunk_count"] >= 1
    assert data["filename"] == "test.pdf"

def test_document_set_version_bumped(client_with_project):
    client, project_id, headers = client_with_project
    proj_before = client.get(f"/projects/{project_id}", headers=headers).json()
    version_before = proj_before["document_set_version"]

    client.post("/documents/upload", json={
        "project_id": project_id,
        "filename": "doc.pdf",
        "category": "artikel",
        "pages": [{"page_number": 1, "text": " ".join(["word"] * 150)}]
    }, headers=headers)

    proj_after = client.get(f"/projects/{project_id}", headers=headers).json()
    assert proj_after["document_set_version"] == version_before + 1


import asyncio

@pytest.mark.asyncio
async def test_embed_single():
    from app.services.embedding_pool import EmbeddingPool
    pool = EmbeddingPool(num_workers=1)
    await pool.start()
    try:
        embedding = await pool.embed("ini adalah teks ujian untuk embedding")
        assert len(embedding) == 384
        assert isinstance(embedding[0], float)
    finally:
        await pool.stop()

@pytest.mark.asyncio
async def test_embed_batch():
    from app.services.embedding_pool import EmbeddingPool
    pool = EmbeddingPool(num_workers=1)
    await pool.start()
    try:
        texts = ["teks pertama", "teks kedua", "teks ketiga"]
        embeddings = await pool.embed_batch(texts)
        assert len(embeddings) == 3
        assert all(len(e) == 384 for e in embeddings)
    finally:
        await pool.stop()

@pytest.mark.asyncio
async def test_embed_consistent():
    from app.services.embedding_pool import EmbeddingPool
    pool = EmbeddingPool(num_workers=1)
    await pool.start()
    try:
        text = "kajian kuantitatif untuk penyelidikan"
        e1 = await pool.embed(text)
        e2 = await pool.embed(text)
        # Same text should produce same embedding (deterministic)
        assert e1 == e2
    finally:
        await pool.stop()

from app.services.rag_pipeline import mmr_rerank, get_retrieval_k

def test_mmr_returns_k_results():
    candidates = [
        {"chunk_id": f"c{i}", "text": f"text {i}", "similarity": 0.9 - i*0.05, "embedding": []}
        for i in range(5)
    ]
    result = mmr_rerank(candidates, k=3)
    assert len(result) == 3

def test_mmr_respects_similarity_order():
    candidates = [
        {"chunk_id": "a", "text": "high sim", "similarity": 0.95, "embedding": []},
        {"chunk_id": "b", "text": "low sim", "similarity": 0.50, "embedding": []},
    ]
    result = mmr_rerank(candidates, k=2)
    # Highest similarity should be first
    assert result[0]["chunk_id"] == "a"

def test_get_retrieval_k_deep():
    assert get_retrieval_k("deep", 5) == 12

def test_get_retrieval_k_many_docs():
    assert get_retrieval_k("normal", 15) == 10

def test_get_retrieval_k_few_docs():
    assert get_retrieval_k("normal", 5) == 6


# --- Task 14: Output Modes Verify ---

def test_output_mode_kredit_costs():
    from app.services.llm_provider import KREDIT_COST
    assert KREDIT_COST["qa"] == 1
    assert KREDIT_COST["qa_deep"] == 3
    assert KREDIT_COST["key_findings"] == 3
    assert KREDIT_COST["executive_summary"] == 5
    assert KREDIT_COST["literature_review"] == 10


def test_invalid_output_mode_rejected():
    """Invalid output mode patut return 400."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from app.services.auth_service import create_jwt

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        with patch("app.database._db_path", db_path):
            from app.database import init_db
            init_db(db_path)
            from app.main import app
            headers = {"Authorization": f"Bearer {create_jwt({'user_id':'u1','email':'u@t.com'})}"}
            with TestClient(app) as c:
                c.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)
                projects = c.get("/projects", headers=headers).json()
                pid = projects[0]["id"]
                r = c.post(f"/projects/{pid}/query",
                           json={"query": "test", "output_mode": "invalid_mode"},
                           headers=headers)
                assert r.status_code == 400


def test_all_valid_output_modes_accepted():
    from app.routers.rag import OUTPUT_MODES
    expected = {"qa", "literature_review", "executive_summary", "key_findings", "research_gap", "discovery", "proposal_extract"}
    assert OUTPUT_MODES == expected


# --- Task 3: Discovery + Proposal modes ---

import tempfile

@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test_task3.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            yield c

@pytest.fixture
def auth_headers():
    from app.services.auth_service import create_jwt
    token = create_jwt({"user_id": "user-t3", "email": "t3@test.com"})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def project_id(client, auth_headers):
    r = client.post("/projects", json={"title": "Task3 Project", "research_mode": "general"}, headers=auth_headers)
    return r.json()["id"]


def test_discovery_mode_rejected_for_unknown_output_mode(client, auth_headers, project_id):
    # sanity check — typo mode ditolak
    r = client.post(f"/projects/{project_id}/query",
                    json={"query": "isu penyelidikan saya", "output_mode": "discover"},
                    headers=auth_headers)
    assert r.status_code == 400

def test_discovery_mode_accepted(client, auth_headers, project_id, monkeypatch):
    async def mock_llm(*args, **kwargs):
        return {"content": "Discovery response", "tokens_used": 10, "model": "mock"}
    async def mock_embed(*args, **kwargs):
        return [0.1] * 384
    monkeypatch.setattr("app.routers.rag.embedding_pool.embed", mock_embed)
    monkeypatch.setattr("app.routers.rag.query_llm", mock_llm)
    # Need at least one chunk — create via upload first
    # (tes ini assume chunks sedia ada, skip jika empty-chunk path diambil)
    r = client.post(f"/projects/{project_id}/query",
                    json={"query": "isu penyelidikan saya", "output_mode": "discovery"},
                    headers=auth_headers)
    # Either 200 (chunks exist) or the "tiada dokumen" 200 path — both are fine, just not 400
    assert r.status_code == 200

def test_proposal_extract_mode_accepted(client, auth_headers, project_id, monkeypatch):
    async def mock_llm(*args, **kwargs):
        return {"content": "Ekstrak proposal", "tokens_used": 20, "model": "mock"}
    async def mock_embed(*args, **kwargs):
        return [0.1] * 384
    monkeypatch.setattr("app.routers.rag.embedding_pool.embed", mock_embed)
    monkeypatch.setattr("app.routers.rag.query_llm", mock_llm)
    r = client.post(f"/projects/{project_id}/query",
                    json={"query": "ekstrak proposal", "output_mode": "proposal_extract"},
                    headers=auth_headers)
    assert r.status_code == 200
