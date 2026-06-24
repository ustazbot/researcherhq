import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.services.auth_service import create_jwt
from app.routers.rag import _cache_key, normalize_query, _emb_to_blob


def make_headers(user_id="user-c1", email="c1@test.com"):
    token = create_jwt({"user_id": user_id, "email": email})
    return {"Authorization": f"Bearer {token}"}


FAKE_EMB = [0.1] * 384
FAKE_ANSWER = "Jawapan cache ujian."


@pytest.fixture
def client_with_project(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            headers = make_headers()
            r = c.post("/projects", json={"title": "Proj Cache", "research_mode": "general"},
                       headers=headers)
            proj_id = r.json()["id"]
            yield c, headers, proj_id, db_path


def test_same_query_returns_cached(client_with_project):
    """Soalan sama dalam projek sama patut return cached response (kredit_used=0)."""
    import sqlite3
    import sqlite_vec as sv
    client, headers, proj_id, db_path = client_with_project

    query_text = "apa metodologi kajian ini?"

    # Pre-insert cache entry
    conn = sqlite3.connect(db_path)
    sv.load(conn)
    import uuid
    from datetime import datetime
    cache_id = _cache_key(query_text, proj_id, 1)
    conn.execute(
        """INSERT INTO query_cache
           (id, project_id, query_normalized, query_embedding, document_set_version,
            response, source_chunks, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cache_id, proj_id, normalize_query(query_text), _emb_to_blob(FAKE_EMB),
         1, FAKE_ANSWER, "[]", datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

    with patch("app.services.embedding_pool.EmbeddingPool.embed", new_callable=AsyncMock,
               return_value=FAKE_EMB):
        r = client.post(f"/projects/{proj_id}/query",
                        json={"query": query_text, "output_mode": "qa"},
                        headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == FAKE_ANSWER
    assert data["kredit_used"] == 0
    assert data.get("cache_hit") is True


def test_cache_invalidated_on_upload(client_with_project):
    """Cache dengan version lama tidak terpakai bila document_set_version berubah."""
    import sqlite3
    import sqlite_vec as sv
    client, headers, proj_id, db_path = client_with_project

    query_text = "terangkan metodologi kajian"

    # Pre-insert cache entry for version 1
    conn = sqlite3.connect(db_path)
    sv.load(conn)
    from datetime import datetime
    cache_id_v1 = _cache_key(query_text, proj_id, 1)
    conn.execute(
        """INSERT INTO query_cache
           (id, project_id, query_normalized, query_embedding, document_set_version,
            response, source_chunks, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cache_id_v1, proj_id, normalize_query(query_text), _emb_to_blob(FAKE_EMB),
         1, FAKE_ANSWER, "[]", datetime.utcnow().isoformat())
    )
    # Bump version to 2 (simulating a new document upload)
    conn.execute("UPDATE projects SET document_set_version = 2 WHERE id = ?", (proj_id,))
    conn.commit()
    conn.close()

    # Query with same text but project is now version 2 — should MISS cache
    # Cache miss → no chunks → llm_knowledge fallback (mock to avoid real API call)
    async def _mock_llm(*args, **kwargs):
        return {"content": "Jawapan llm_knowledge.", "tokens_used": 5, "model": "mock"}

    with patch("app.services.embedding_pool.EmbeddingPool.embed", new_callable=AsyncMock,
               return_value=FAKE_EMB), \
         patch("app.routers.rag.query_llm", new=_mock_llm), \
         patch("app.routers.rag.settings.perplexity_api_key", ""):
        r = client.post(f"/projects/{proj_id}/query",
                        json={"query": query_text, "output_mode": "qa"},
                        headers=headers)

    assert r.status_code == 200
    data = r.json()
    assert data.get("cache_hit") is not True
    assert data["source_type"] in ("llm_knowledge", "web_search")


def test_retrieval_deterministic():
    """mmr_rerank dengan input sama kena return urutan sama (tie-break by chunk_id)."""
    from app.services.rag_pipeline import mmr_rerank

    candidates = [
        {"chunk_id": "z", "text": "teks z", "similarity": 0.8},
        {"chunk_id": "a", "text": "teks a", "similarity": 0.8},
        {"chunk_id": "m", "text": "teks m", "similarity": 0.9},
    ]
    r1 = mmr_rerank(candidates.copy(), k=2)
    r2 = mmr_rerank(candidates.copy(), k=2)
    assert [x["chunk_id"] for x in r1] == [x["chunk_id"] for x in r2]
    # m has highest sim, should be first
    assert r1[0]["chunk_id"] == "m"


# Near-match cache test vectors
_EMBED_A = [1.0] + [0.0] * 383
_EMBED_B_NEAR = [0.98, 0.1] + [0.0] * 382   # cosine with A ≈ 0.995, above 0.95 threshold
_EMBED_C_FAR = [0.0, 1.0] + [0.0] * 382     # cosine with A = 0.0, below 0.90


def test_near_match_query_returns_cached(client_with_project):
    """Query dengan embedding hampir sama (cosine > 0.95) patut hit near-match cache."""
    import sqlite3
    import sqlite_vec as sv
    client, headers, proj_id, db_path = client_with_project

    # Seed cache: "soalan asal" with EMBED_A, doc_version=1
    conn = sqlite3.connect(db_path)
    sv.load(conn)
    from datetime import datetime
    cache_id = _cache_key("soalan asal", proj_id, 1)
    conn.execute(
        """INSERT INTO query_cache
           (id, project_id, query_normalized, query_embedding, document_set_version,
            response, source_chunks, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cache_id, proj_id, normalize_query("soalan asal"), _emb_to_blob(_EMBED_A),
         1, "Jawapan near-match.", "[]", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    # Query with DIFFERENT text (different hash → exact match fails)
    # but embed returns EMBED_B_NEAR (cosine > 0.95 → near-match hits)
    with patch("app.services.embedding_pool.EmbeddingPool.embed", new_callable=AsyncMock,
               return_value=_EMBED_B_NEAR):
        r = client.post(
            f"/projects/{proj_id}/query",
            json={"query": "soalan berbeza tapi hampir sama", "output_mode": "qa"},
            headers=headers,
        )

    assert r.status_code == 200
    data = r.json()
    assert data.get("cache_hit") is True, f"Expected cache_hit=True, got: {data}"
    assert data["kredit_used"] == 0


def test_dissimilar_query_misses_cache(client_with_project):
    """Query dengan embedding jauh (cosine < 0.90) tidak patut hit cache."""
    import sqlite3
    import sqlite_vec as sv
    client, headers, proj_id, db_path = client_with_project

    # Seed cache with EMBED_A
    conn = sqlite3.connect(db_path)
    sv.load(conn)
    from datetime import datetime
    cache_id = _cache_key("soalan pertama", proj_id, 1)
    conn.execute(
        """INSERT INTO query_cache
           (id, project_id, query_normalized, query_embedding, document_set_version,
            response, source_chunks, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (cache_id, proj_id, normalize_query("soalan pertama"), _emb_to_blob(_EMBED_A),
         1, "Jawapan pertama.", "[]", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()

    # Orthogonal embedding → cosine = 0.0 → must miss cache → falls to retrieval
    # No documents → llm_knowledge fallback (mock to avoid real API call)
    async def _mock_llm(*args, **kwargs):
        return {"content": "Jawapan llm_knowledge.", "tokens_used": 5, "model": "mock"}

    with patch("app.services.embedding_pool.EmbeddingPool.embed", new_callable=AsyncMock,
               return_value=_EMBED_C_FAR), \
         patch("app.routers.rag.query_llm", new=_mock_llm), \
         patch("app.routers.rag.settings.perplexity_api_key", ""):
        r = client.post(
            f"/projects/{proj_id}/query",
            json={"query": "soalan yang sama sekali berbeza", "output_mode": "qa"},
            headers=headers,
        )

    assert r.status_code == 200
    data = r.json()
    assert data.get("cache_hit") is not True, f"Expected no cache_hit, got: {data}"
