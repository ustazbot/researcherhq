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
    # Since no real chunks and no LLM mock, we expect the "no documents" response
    with patch("app.services.embedding_pool.EmbeddingPool.embed", new_callable=AsyncMock,
               return_value=FAKE_EMB):
        r = client.post(f"/projects/{proj_id}/query",
                        json={"query": query_text, "output_mode": "qa"},
                        headers=headers)

    assert r.status_code == 200
    data = r.json()
    # Cache miss → falls through to retrieval → no chunks → "tiada dokumen"
    assert data.get("cache_hit") is not True
    assert "tiada dokumen" in data["answer"].lower() or data["kredit_used"] == 0


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
