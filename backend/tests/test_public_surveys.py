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


def _seed(db_path, uid, email):
    conn = sqlite3.connect(db_path)
    conn.execute(
        """INSERT OR IGNORE INTO users (id, email, tier, kredit_remaining, kredit_total,
           kredit_subscription, kredit_topup, tokens_used_internal, reset_date, created_at)
           VALUES (?, ?, 'pro', 500, 500, 500, 0, 0, ?, ?)""",
        (uid, email, _reset_date(), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def _setup_published(client, mode="actual", cap=None):
    c, db_path = client
    token, uid, email = make_token()
    _seed(db_path, uid, email)
    pid = str(uuid.uuid4())
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO projects (id, user_id, title, research_mode, created_at) VALUES (?,?,'P','general',?)",
                 (pid, uid, datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    headers = {"Authorization": f"Bearer {token}"}
    sid = c.post(f"/projects/{pid}/surveys", json={}, headers=headers).json()["id"]
    sec = c.post(f"/surveys/{sid}/sections", json={"title": "Sec"}, headers=headers).json()["id"]
    c.post(f"/sections/{sec}/questions",
           json={"question_text": "Rate", "question_type": "likert", "options": ["1", "2", "3", "4", "5"], "likert_points": 5},
           headers=headers)
    c.post(f"/sections/{sec}/questions",
           json={"question_text": "Pick", "question_type": "mcq", "options": ["A", "B"]}, headers=headers)
    body = {"mode": mode}
    if cap is not None:
        body["response_cap"] = cap
    share_token = c.post(f"/surveys/{sid}/publish", json=body, headers=headers).json()["share_token"]
    qids = _qids(db_path, sid)
    return c, db_path, headers, sid, share_token, qids


def _qids(db_path, sid):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT q.id, q.question_type FROM survey_questions q JOIN survey_sections s ON s.id=q.section_id "
        "WHERE s.survey_id=? ORDER BY q.id", (sid,)).fetchall()
    conn.close()
    return [(r["id"], r["question_type"]) for r in rows]


def _valid_answers(qids):
    out = []
    for qid, qtype in qids:
        out.append({"question_id": qid, "answer_value": "3" if qtype == "likert" else "A"})
    return out


# ── GET public structure ─────────────────────────────────────────

def test_public_get_hides_internal_ids(client):
    c, db_path, headers, sid, token, qids = _setup_published(client)
    r = c.get(f"/public/surveys/{token}")
    assert r.status_code == 200
    body = r.json()
    raw = r.text
    assert "user_id" not in raw
    assert "project_id" not in raw
    assert "@" not in raw  # no email
    assert body["title"]
    assert len(body["sections"]) == 1


def test_public_get_bad_token_404(client):
    c, db_path = client
    r = c.get("/public/surveys/NONEXISTENT")
    assert r.status_code == 404


def test_public_get_draft_410(client):
    c, db_path, headers, sid, token, qids = _setup_published(client)
    c.post(f"/surveys/{sid}/close", headers=headers)   # published → closed
    r = c.get(f"/public/surveys/{token}")
    assert r.status_code == 410


# ── POST submit ──────────────────────────────────────────────────

def test_submit_actual_sets_is_pilot_0(client):
    c, db_path, headers, sid, token, qids = _setup_published(client, mode="actual")
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r = c.post(f"/public/surveys/{token}/responses",
                   json={"answers": _valid_answers(qids), "turnstile_token": "t"})
    assert r.status_code == 201
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT is_pilot FROM survey_responses WHERE survey_id=?", (sid,)).fetchone()
    conn.close()
    assert row[0] == 0


def test_submit_pilot_sets_is_pilot_1_ignoring_client(client):
    c, db_path, headers, sid, token, qids = _setup_published(client, mode="pilot")
    payload = {"answers": _valid_answers(qids), "turnstile_token": "t", "is_pilot": 0}  # client lies
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r = c.post(f"/public/surveys/{token}/responses", json=payload)
    assert r.status_code == 201
    conn = sqlite3.connect(db_path)
    row = conn.execute("SELECT is_pilot FROM survey_responses WHERE survey_id=?", (sid,)).fetchone()
    conn.close()
    assert row[0] == 1  # server-side wins


def test_submit_turnstile_fail_403(client):
    c, db_path, headers, sid, token, qids = _setup_published(client)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=False):
        r = c.post(f"/public/surveys/{token}/responses",
                   json={"answers": _valid_answers(qids), "turnstile_token": "bad"})
    assert r.status_code == 403


def test_submit_foreign_question_id_422(client):
    c, db_path, headers, sid, token, qids = _setup_published(client)
    bad = [{"question_id": 999999, "answer_value": "3"}] + _valid_answers(qids)[1:]
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r = c.post(f"/public/surveys/{token}/responses",
                   json={"answers": bad, "turnstile_token": "t"})
    assert r.status_code == 422


def test_submit_likert_out_of_range_422(client):
    c, db_path, headers, sid, token, qids = _setup_published(client)
    answers = _valid_answers(qids)
    # set the likert answer to 9 (out of 1..5)
    for a in answers:
        pass
    likert_qid = [qid for qid, qt in qids if qt == "likert"][0]
    answers = [{"question_id": qid, "answer_value": ("9" if qid == likert_qid else "A")} for qid, qt in qids]
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r = c.post(f"/public/surveys/{token}/responses",
                   json={"answers": answers, "turnstile_token": "t"})
    assert r.status_code == 422


def test_submit_missing_answer_422_no_partial_insert(client):
    c, db_path, headers, sid, token, qids = _setup_published(client)
    partial = _valid_answers(qids)[:1]  # only 1 of 2 questions
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r = c.post(f"/public/surveys/{token}/responses",
                   json={"answers": partial, "turnstile_token": "t"})
    assert r.status_code == 422
    conn = sqlite3.connect(db_path)
    n_resp = conn.execute("SELECT COUNT(*) FROM survey_responses WHERE survey_id=?", (sid,)).fetchone()[0]
    n_ans = conn.execute("SELECT COUNT(*) FROM survey_answers").fetchone()[0]
    conn.close()
    assert n_resp == 0 and n_ans == 0  # atomic: nothing inserted


def test_submit_cap_reached_409(client):
    c, db_path, headers, sid, token, qids = _setup_published(client, mode="pilot", cap=1)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r1 = c.post(f"/public/surveys/{token}/responses",
                    json={"answers": _valid_answers(qids), "turnstile_token": "t"})
        assert r1.status_code == 201
        # second submit exceeds cap=1 (different behaviour from dedup — use fresh IP via header)
        r2 = c.post(f"/public/surveys/{token}/responses",
                    json={"answers": _valid_answers(qids), "turnstile_token": "t"},
                    headers={"X-Real-IP": "9.9.9.9"})
    assert r2.status_code == 409


def test_submit_dedup_60s_429(client):
    c, db_path, headers, sid, token, qids = _setup_published(client, mode="actual")
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        r1 = c.post(f"/public/surveys/{token}/responses",
                    json={"answers": _valid_answers(qids), "turnstile_token": "t"},
                    headers={"X-Real-IP": "5.5.5.5"})
        assert r1.status_code == 201
        # same IP again within 60s → dedup 429
        r2 = c.post(f"/public/surveys/{token}/responses",
                    json={"answers": _valid_answers(qids), "turnstile_token": "t"},
                    headers={"X-Real-IP": "5.5.5.5"})
    assert r2.status_code == 429


def test_no_raw_ip_stored_only_hash(client):
    c, db_path, headers, sid, token, qids = _setup_published(client)
    with patch("app.routers.public_surveys.verify_turnstile_token", return_value=True):
        c.post(f"/public/surveys/{token}/responses",
               json={"answers": _valid_answers(qids), "turnstile_token": "t"},
               headers={"X-Real-IP": "8.8.8.8"})
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM survey_responses WHERE survey_id=?", (sid,)).fetchone()
    cols = row.keys()
    conn.close()
    assert "ip_hash" in cols
    assert "ip" not in cols and "user_agent" not in cols
    assert row["ip_hash"] != "8.8.8.8"          # not raw
    assert len(row["ip_hash"]) == 64            # sha256 hex
