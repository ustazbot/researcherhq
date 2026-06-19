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
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        from app.database import init_db
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            yield c

def test_create_project(client):
    r = client.post("/projects", json={
        "title": "Tesis Saya",
        "research_mode": "general",
        "field": "Sains Sosial"
    }, headers=make_headers())
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Tesis Saya"
    assert data["research_mode"] == "general"
    assert data["field"] == "Sains Sosial"
    assert "id" in data

def test_list_projects(client):
    h1 = make_headers("user-1", "u1@test.com")
    h2 = make_headers("user-2", "u2@test.com")
    client.post("/projects", json={"title": "Proj A", "research_mode": "general"}, headers=h1)
    client.post("/projects", json={"title": "Proj B", "research_mode": "law"}, headers=h2)
    r1 = client.get("/projects", headers=h1)
    r2 = client.get("/projects", headers=h2)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(r1.json()) + len(r2.json()) == 2

def test_project_isolation(client):
    h1 = make_headers("user-1", "u1@test.com")
    h2 = make_headers("user-2", "u2@test.com")
    client.post("/projects", json={"title": "User1 Project", "research_mode": "general"}, headers=h1)
    r = client.get("/projects", headers=h2)
    assert r.json() == []

def test_free_tier_project_limit(client):
    headers = make_headers()
    # First project should succeed
    r1 = client.post("/projects", json={"title": "P1", "research_mode": "general"}, headers=headers)
    assert r1.status_code == 201
    # Second project should fail (free tier = max 1)
    r2 = client.post("/projects", json={"title": "P2", "research_mode": "general"}, headers=headers)
    assert r2.status_code == 403

def test_get_project(client):
    headers = make_headers()
    r_create = client.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)
    proj_id = r_create.json()["id"]
    r = client.get(f"/projects/{proj_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == proj_id

def test_delete_project(client):
    headers = make_headers()
    r_create = client.post("/projects", json={"title": "T", "research_mode": "general"}, headers=headers)
    proj_id = r_create.json()["id"]
    r_del = client.delete(f"/projects/{proj_id}", headers=headers)
    assert r_del.status_code == 204
    r_get = client.get(f"/projects/{proj_id}", headers=headers)
    assert r_get.status_code == 404

def test_invalid_research_mode(client):
    r = client.post("/projects", json={"title": "T", "research_mode": "invalid_mode"}, headers=make_headers())
    assert r.status_code == 400
