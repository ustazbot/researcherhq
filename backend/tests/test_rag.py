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
