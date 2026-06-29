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

def create_proj(client, title="My Project", user_id="user-1"):
    r = client.post("/projects", json={"title": title, "research_mode": "general"},
                    headers=make_headers(user_id))
    assert r.status_code == 201
    return r.json()["id"]

def test_patch_valid_title(client):
    pid = create_proj(client)
    r = client.patch(f"/projects/{pid}", json={"title": "New Title"}, headers=make_headers())
    assert r.status_code == 200
    assert r.json()["title"] == "New Title"

def test_patch_empty_string_title(client):
    pid = create_proj(client)
    r = client.patch(f"/projects/{pid}", json={"title": ""}, headers=make_headers())
    assert r.status_code == 400

def test_patch_whitespace_only_title(client):
    pid = create_proj(client)
    r = client.patch(f"/projects/{pid}", json={"title": "   "}, headers=make_headers())
    assert r.status_code == 400

def test_patch_wrong_user(client):
    pid = create_proj(client, user_id="user-1")
    r = client.patch(f"/projects/{pid}", json={"title": "Hacked"}, headers=make_headers("user-2", "u2@test.com"))
    assert r.status_code == 404

def test_patch_nonexistent_project(client):
    # Ensure user exists first
    create_proj(client)
    r = client.patch("/projects/does-not-exist", json={"title": "X"}, headers=make_headers())
    assert r.status_code == 404

def test_patch_no_title_field(client):
    pid = create_proj(client, title="Original")
    r = client.patch(f"/projects/{pid}", json={}, headers=make_headers())
    assert r.status_code == 200
    assert r.json()["title"] == "Original"

def test_delete_still_works(client):
    pid = create_proj(client)
    r = client.delete(f"/projects/{pid}", headers=make_headers())
    assert r.status_code == 204
    r2 = client.get(f"/projects/{pid}", headers=make_headers())
    assert r2.status_code == 404
