import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import sqlite3
import uuid
from datetime import datetime, date
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import init_db
from app.services.auth_service import create_jwt


def make_token(user_id=None, email=None):
    uid = user_id or str(uuid.uuid4())
    em = email or f"pub_{uuid.uuid4().hex[:6]}@test.com"
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
    return date(today.year + (today.month == 12), (today.month % 12) + 1, 1).isoformat()


def _seed_user(db_path, uid, email, tier="pro"):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO users
           (id, email, tier, kredit_remaining, kredit_total, kredit_subscription, kredit_topup,
            tokens_used_internal, reset_date, created_at)
           VALUES (?, ?, ?, 500, 500, 500, 0, 0, ?, ?)""",
        (uid, email, tier, _reset_date(), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def _seed_project(db_path, pid, uid):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO projects (id, user_id, title, research_mode, created_at) VALUES (?,?,'P','general',?)",
        (pid, uid, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def _setup(client, tier="pro"):
    c, db_path = client
    token, uid, email = make_token()
    _seed_user(db_path, uid, email, tier=tier)
    pid = str(uuid.uuid4())
    _seed_project(db_path, pid, uid)
    return c, db_path, uid, pid, {"Authorization": f"Bearer {token}"}


def _build_survey(c, pid, headers, n_questions=2):
    sid = c.post(f"/projects/{pid}/surveys", json={}, headers=headers).json()["id"]
    sec = c.post(f"/surveys/{sid}/sections", json={"title": "Section A"}, headers=headers).json()["id"]
    for i in range(n_questions):
        c.post(f"/sections/{sec}/questions",
               json={"question_text": f"Q{i}", "question_type": "likert",
                     "options": ["1", "2", "3", "4", "5"], "likert_points": 5},
               headers=headers)
    return sid, sec


# ── Pro-gating (36A patch) ───────────────────────────────────────

def test_free_user_cannot_create_survey(client):
    c, db_path, uid, pid, headers = _setup(client, tier="free")
    r = c.post(f"/projects/{pid}/surveys", json={}, headers=headers)
    assert r.status_code == 403


def test_pro_user_can_create_survey(client):
    c, db_path, uid, pid, headers = _setup(client, tier="pro")
    r = c.post(f"/projects/{pid}/surveys", json={}, headers=headers)
    assert r.status_code == 201


# ── Publish ──────────────────────────────────────────────────────

def test_publish_pilot_generates_token_and_clamps_cap(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, _ = _build_survey(c, pid, headers)
    r = c.post(f"/surveys/{sid}/publish", json={"mode": "pilot", "response_cap": 999}, headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pilot"
    assert body["mode"] == "pilot"
    assert body["share_token"]
    assert body["response_cap"] == 50  # clamped to pilot max


def test_publish_actual_clamps_cap(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, _ = _build_survey(c, pid, headers)
    r = c.post(f"/surveys/{sid}/publish", json={"mode": "actual", "response_cap": 99999}, headers=headers)
    assert r.json()["response_cap"] == 1000
    assert r.json()["status"] == "published"


def test_publish_empty_survey_rejected(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid = c.post(f"/projects/{pid}/surveys", json={}, headers=headers).json()["id"]
    r = c.post(f"/surveys/{sid}/publish", json={"mode": "pilot"}, headers=headers)
    assert r.status_code == 400


# ── Frozen structure while collecting ────────────────────────────

def test_structure_frozen_during_pilot(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    c.post(f"/surveys/{sid}/publish", json={"mode": "pilot"}, headers=headers)
    assert c.post(f"/surveys/{sid}/sections", json={"title": "X"}, headers=headers).status_code == 409
    assert c.post(f"/sections/{sec}/questions", json={"question_text": "Y"}, headers=headers).status_code == 409
    assert c.patch(f"/sections/{sec}", json={"title": "Z"}, headers=headers).status_code == 409


def test_structure_frozen_during_published(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    c.post(f"/surveys/{sid}/publish", json={"mode": "actual"}, headers=headers)
    assert c.post(f"/surveys/{sid}/sections", json={"title": "X"}, headers=headers).status_code == 409


# ── Unlock (pilot) ───────────────────────────────────────────────

def _submit_public(c, token, sid_questions, mock_ok=True):
    """Submit a public response. sid_questions = list of question ids."""
    answers = [{"question_id": qid, "answer_value": "3"} for qid in sid_questions]
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True) if mock_ok else \
            patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        return c.post(f"/public/surveys/{token}/responses",
                      json={"answers": answers, "turnstile_token": "tok"})


def _question_ids(db_path, sid):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT q.id FROM survey_questions q JOIN survey_sections s ON s.id=q.section_id
           WHERE s.survey_id=? ORDER BY q.id""", (sid,)).fetchall()
    conn.close()
    return [r["id"] for r in rows]


def test_unlock_keeps_pilot_responses(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    token = c.post(f"/surveys/{sid}/publish", json={"mode": "pilot"}, headers=headers).json()["share_token"]
    qids = _question_ids(db_path, sid)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r = c.post(f"/public/surveys/{token}/responses",
                   json={"answers": [{"question_id": q, "answer_value": "4"} for q in qids], "turnstile_token": "t"})
    assert r.status_code == 201
    # close then unlock
    assert c.post(f"/surveys/{sid}/close", headers=headers).status_code == 200
    assert c.post(f"/surveys/{sid}/unlock", headers=headers).json()["status"] == "draft"
    # pilot response still present
    conn = sqlite3.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM survey_responses WHERE survey_id=? AND is_pilot=1", (sid,)).fetchone()[0]
    conn.close()
    assert n == 1


def test_unlock_actual_rejected(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    c.post(f"/surveys/{sid}/publish", json={"mode": "actual"}, headers=headers)
    c.post(f"/surveys/{sid}/close", headers=headers)
    # closed actual → unlock should 409
    assert c.post(f"/surveys/{sid}/unlock", headers=headers).status_code == 409


def test_publish_actual_after_pilot_same_token_new_label(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    token1 = c.post(f"/surveys/{sid}/publish", json={"mode": "pilot"}, headers=headers).json()["share_token"]
    qids = _question_ids(db_path, sid)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r1 = c.post(f"/public/surveys/{token1}/responses",
                    json={"answers": [{"question_id": q, "answer_value": "2"} for q in qids], "turnstile_token": "t"},
                    headers={"X-Real-IP": "1.1.1.1"})
        assert r1.status_code == 201
    c.post(f"/surveys/{sid}/close", headers=headers)
    c.post(f"/surveys/{sid}/unlock", headers=headers)
    token2 = c.post(f"/surveys/{sid}/publish", json={"mode": "actual"}, headers=headers).json()["share_token"]
    assert token1 == token2  # same link
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r2 = c.post(f"/public/surveys/{token2}/responses",
                    json={"answers": [{"question_id": q, "answer_value": "5"} for q in qids], "turnstile_token": "t"},
                    headers={"X-Real-IP": "2.2.2.2"})
        assert r2.status_code == 201
    conn = sqlite3.connect(db_path)
    pilot = conn.execute("SELECT COUNT(*) FROM survey_responses WHERE survey_id=? AND is_pilot=1", (sid,)).fetchone()[0]
    actual = conn.execute("SELECT COUNT(*) FROM survey_responses WHERE survey_id=? AND is_pilot=0", (sid,)).fetchone()[0]
    conn.close()
    assert pilot == 1 and actual == 1


def test_cascade_delete_question_removes_pilot_answers(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    token = c.post(f"/surveys/{sid}/publish", json={"mode": "pilot"}, headers=headers).json()["share_token"]
    qids = _question_ids(db_path, sid)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        c.post(f"/public/surveys/{token}/responses",
               json={"answers": [{"question_id": q, "answer_value": "3"} for q in qids], "turnstile_token": "t"})
    c.post(f"/surveys/{sid}/close", headers=headers)
    c.post(f"/surveys/{sid}/unlock", headers=headers)
    # delete one question → its pilot answers gone, other answers remain
    r = c.delete(f"/questions/{qids[0]}", headers=headers)
    assert r.status_code == 204
    conn = sqlite3.connect(db_path)
    left_for_deleted = conn.execute("SELECT COUNT(*) FROM survey_answers WHERE question_id=?", (qids[0],)).fetchone()[0]
    left_for_other = conn.execute("SELECT COUNT(*) FROM survey_answers WHERE question_id=?", (qids[1],)).fetchone()[0]
    conn.close()
    assert left_for_deleted == 0
    assert left_for_other == 1


# ── Unpublish (actual) ───────────────────────────────────────────

def test_unpublish_actual_zero_responses_ok(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    c.post(f"/surveys/{sid}/publish", json={"mode": "actual"}, headers=headers)
    assert c.post(f"/surveys/{sid}/unpublish", headers=headers).json()["status"] == "draft"


def test_unpublish_actual_with_responses_409_then_ok_after_delete(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    token = c.post(f"/surveys/{sid}/publish", json={"mode": "actual"}, headers=headers).json()["share_token"]
    qids = _question_ids(db_path, sid)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        c.post(f"/public/surveys/{token}/responses",
               json={"answers": [{"question_id": q, "answer_value": "3"} for q in qids], "turnstile_token": "t"})
    assert c.post(f"/surveys/{sid}/unpublish", headers=headers).status_code == 409
    assert c.delete(f"/surveys/{sid}/responses?type=actual", headers=headers).status_code == 204
    assert c.post(f"/surveys/{sid}/unpublish", headers=headers).json()["status"] == "draft"


# ── Tier limit ───────────────────────────────────────────────────

def test_sixth_active_survey_rejected(client):
    c, db_path, uid, pid, headers = _setup(client)
    tokens = []
    for i in range(5):
        sid, _ = _build_survey(c, pid, headers)
        r = c.post(f"/surveys/{sid}/publish", json={"mode": "pilot"}, headers=headers)
        assert r.status_code == 200
    sid6, _ = _build_survey(c, pid, headers)
    r = c.post(f"/surveys/{sid6}/publish", json={"mode": "actual"}, headers=headers)
    assert r.status_code == 403


# ── Owner responses dashboard + CSV ──────────────────────────────

def test_responses_dashboard_and_ownership(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    token = c.post(f"/surveys/{sid}/publish", json={"mode": "actual"}, headers=headers).json()["share_token"]
    qids = _question_ids(db_path, sid)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        c.post(f"/public/surveys/{token}/responses",
               json={"answers": [{"question_id": q, "answer_value": "3"} for q in qids], "turnstile_token": "t"})
    r = c.get(f"/surveys/{sid}/responses?type=actual", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["actual"] == 1
    rid = body["responses"][0]["id"]
    # detail
    detail = c.get(f"/surveys/{sid}/responses/{rid}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["answers"]) == len(qids)
    # ownership: other user 404
    other_token, ouid, oemail = make_token()
    _seed_user(db_path, ouid, oemail)
    assert c.get(f"/surveys/{sid}/responses", headers={"Authorization": f"Bearer {other_token}"}).status_code == 404
    # delete one
    assert c.delete(f"/surveys/{sid}/responses/{rid}", headers=headers).status_code == 204


def test_csv_export_has_is_pilot_and_rows(client):
    c, db_path, uid, pid, headers = _setup(client)
    sid, sec = _build_survey(c, pid, headers)
    token = c.post(f"/surveys/{sid}/publish", json={"mode": "actual"}, headers=headers).json()["share_token"]
    qids = _question_ids(db_path, sid)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        c.post(f"/public/surveys/{token}/responses",
               json={"answers": [{"question_id": q, "answer_value": "4"} for q in qids], "turnstile_token": "t"})
    r = c.get(f"/surveys/{sid}/export/csv?type=actual", headers=headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = [ln for ln in r.text.splitlines() if ln.strip()]
    assert "is_pilot" in lines[0]
    assert len(lines) == 2  # header + 1 response
