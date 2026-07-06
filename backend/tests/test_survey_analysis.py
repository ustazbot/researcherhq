import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import io
import json
import sqlite3
import uuid
from datetime import datetime, date
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import init_db
from app.services.auth_service import create_jwt

# ── Fixture data (raw answer values as stored; q4 is reverse-coded) ──────────
# 4 Likert-5 items, q4 is_reversed=1. 10 responses (actual). r10 missing q2.
#   q1 raw = [4,5,3,4,2,5,3,4,2,5]
#   q2 raw = [4,4,3,5,2,5,4,3,3, (missing)]
#   q3 raw = [5,4,3,4,3,5,3,4,2,4]
#   q4 raw = [1,2,3,1,5,2,4,3,5,2]  ->  reversed (6-raw) = [5,4,3,5,1,4,2,3,1,4]
#
# Independently computed (numpy/pandas/scipy, see task fixture derivation):
#   q1: mean 3.7, sd 1.16 (ddof=1)
#   q4 reversed mean = 32/10 = 3.2  (proves reverse-coding applied)
#   construct {q1,q3,q4r} n=10: Cronbach alpha = 0.917
#     alpha-if-deleted: q1 .867, q3 .886, q4 .890
#     corrected item-total r: q1 .851, q3 .871, q4 .869
#   construct {q1,q2,q3,q4r} listwise (drops r10) n=9: alpha = 0.921
#   normality of {q1,q3,q4r} composite: skew -0.631, kurt(excess) -1.22,
#     Shapiro W 0.870, p 0.100
Q1 = [4, 5, 3, 4, 2, 5, 3, 4, 2, 5]
Q2 = [4, 4, 3, 5, 2, 5, 4, 3, 3, None]
Q3 = [5, 4, 3, 4, 3, 5, 3, 4, 2, 4]
Q4 = [1, 2, 3, 1, 5, 2, 4, 3, 5, 2]


def make_token(uid=None, email=None):
    uid = uid or str(uuid.uuid4())
    em = email or f"an_{uuid.uuid4().hex[:6]}@test.com"
    return create_jwt({"user_id": uid, "email": em}), uid, em


@pytest.fixture
def client(tmp_path):
    db_path = str(tmp_path / "test.db")
    with patch("app.database._db_path", db_path):
        init_db(db_path)
        from app.main import app
        with TestClient(app) as c:
            yield c, db_path


def _conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _reset_date():
    t = date.today()
    return date(t.year + (t.month == 12), (t.month % 12) + 1, 1).isoformat()


def _seed(db_path, tier="pro"):
    """Seed user+project+survey+4 likert questions+10 actual responses. Returns ids."""
    uid = str(uuid.uuid4())
    email = f"an_{uuid.uuid4().hex[:6]}@test.com"
    conn = _conn(db_path)
    conn.execute(
        """INSERT INTO users (id, email, tier, kredit_remaining, kredit_total, kredit_subscription,
           kredit_topup, tokens_used_internal, reset_date, created_at)
           VALUES (?,?,?,500,500,500,0,0,?,?)""",
        (uid, email, tier, _reset_date(), datetime.utcnow().isoformat()),
    )
    pid = str(uuid.uuid4())
    conn.execute("INSERT INTO projects (id, user_id, title, research_mode, created_at) VALUES (?,?,'P','general',?)",
                 (pid, uid, datetime.utcnow().isoformat()))
    now = datetime.utcnow().isoformat()
    sid = conn.execute("INSERT INTO surveys (project_id, title, status, created_at, updated_at) VALUES (?,?,'draft',?,?)",
                       (pid, "Survey", now, now)).lastrowid
    secid = conn.execute("INSERT INTO survey_sections (survey_id, title, position) VALUES (?,?,0)",
                         (sid, "Sec")).lastrowid
    qids = []
    for i, rev in enumerate([0, 0, 0, 1]):  # q4 reversed
        qid = conn.execute(
            """INSERT INTO survey_questions (section_id, question_text, question_type, options_json,
               likert_points, is_reversed, position) VALUES (?,?,?,?,?,?,?)""",
            (secid, f"Q{i+1}", "likert", json.dumps(["1", "2", "3", "4", "5"]), 5, rev, i),
        ).lastrowid
        qids.append(qid)
    # 10 actual responses
    for r in range(10):
        rid = conn.execute(
            "INSERT INTO survey_responses (survey_id, is_pilot, submitted_at, ip_hash) VALUES (?,0,?,?)",
            (sid, now, f"hash{r}"),
        ).lastrowid
        for qcol, qid in zip([Q1, Q2, Q3, Q4], qids):
            v = qcol[r]
            if v is None:
                continue
            conn.execute("INSERT INTO survey_answers (response_id, question_id, answer_value) VALUES (?,?,?)",
                         (rid, qid, str(v)))
    conn.commit()
    conn.close()
    token = create_jwt({"user_id": uid, "email": email})
    return {"headers": {"Authorization": f"Bearer {token}"}, "sid": sid, "qids": qids,
            "uid": uid, "db_path": db_path, "pid": pid}


# ── Dataset builder (direct) ─────────────────────────────────────

def test_dataset_reverse_coding_and_pivot(client):
    c, db_path = client
    s = _seed(db_path)
    from app.services.survey_dataset import build_dataframe
    conn = _conn(db_path)
    df = build_dataframe(conn, s["sid"], "actual")
    conn.close()
    q1, q4 = s["qids"][0], s["qids"][3]
    # pivot: 10 rows
    assert df.shape[0] == 10
    # q4 reverse-coded: raw [1,2,3,1,5,2,4,3,5,2] -> [5,4,3,5,1,4,2,3,1,4]
    assert list(df[q4].dropna().astype(int)) == [5, 4, 3, 5, 1, 4, 2, 3, 1, 4]
    assert df[q1].mean() == pytest.approx(3.7, abs=0.001)


def test_dataset_min_responses_422(client):
    c, db_path = client
    s = _seed(db_path)
    from app.services.survey_dataset import build_dataframe
    from fastapi import HTTPException
    conn = _conn(db_path)
    # pilot has 0 responses
    with pytest.raises(HTTPException) as e:
        build_dataframe(conn, s["sid"], "pilot")
    conn.close()
    assert e.value.status_code == 422


# ── Constructs CRUD + validation ─────────────────────────────────

def _mk_construct(c, s, qids, name="Kepuasan"):
    return c.post(f"/surveys/{s['sid']}/constructs",
                  json={"name": name, "question_ids": qids}, headers=s["headers"])


def test_construct_create_and_list(client):
    c, db_path = client
    s = _seed(db_path)
    r = _mk_construct(c, s, [s["qids"][0], s["qids"][2], s["qids"][3]])
    assert r.status_code == 201
    lst = c.get(f"/surveys/{s['sid']}/constructs", headers=s["headers"]).json()
    assert len(lst) == 1
    assert len(lst[0]["question_ids"]) == 3


def test_construct_rejects_non_likert(client):
    c, db_path = client
    s = _seed(db_path)
    # add an mcq question
    conn = _conn(db_path)
    secid = conn.execute("SELECT id FROM survey_sections WHERE survey_id=?", (s["sid"],)).fetchone()["id"]
    mcq = conn.execute(
        "INSERT INTO survey_questions (section_id, question_text, question_type, options_json, position) VALUES (?,?,?,?,9)",
        (secid, "Gender", "mcq", json.dumps(["M", "F"])),
    ).lastrowid
    conn.commit(); conn.close()
    r = _mk_construct(c, s, [s["qids"][0], mcq])
    assert r.status_code == 422


def test_construct_rejects_mixed_likert_points(client):
    c, db_path = client
    s = _seed(db_path)
    conn = _conn(db_path)
    secid = conn.execute("SELECT id FROM survey_sections WHERE survey_id=?", (s["sid"],)).fetchone()["id"]
    q7 = conn.execute(
        "INSERT INTO survey_questions (section_id, question_text, question_type, likert_points, position) VALUES (?,?,?,?,9)",
        (secid, "Q7", "likert", 7),
    ).lastrowid
    conn.commit(); conn.close()
    r = _mk_construct(c, s, [s["qids"][0], q7])  # 5-point + 7-point
    assert r.status_code == 422


def test_construct_ownership_404(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_construct(c, s, [s["qids"][0], s["qids"][2]]).json()["id"]
    other_token, _, _ = make_token()
    r = c.patch(f"/constructs/{cid}", json={"name": "x"}, headers={"Authorization": f"Bearer {other_token}"})
    assert r.status_code == 404


def test_construct_cascade_keeps_analyses(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_construct(c, s, [s["qids"][0], s["qids"][2], s["qids"][3]]).json()["id"]
    a = c.post(f"/surveys/{s['sid']}/analyses",
               json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
               headers=s["headers"])
    assert a.status_code == 200
    aid = a.json()["id"]
    # delete a question -> construct_items cascade, but analysis snapshot stays
    c.delete(f"/questions/{s['qids'][0]}", headers=s["headers"])
    conn = _conn(db_path)
    items = conn.execute("SELECT COUNT(*) FROM survey_construct_items WHERE question_id=?", (s["qids"][0],)).fetchone()[0]
    analyses = conn.execute("SELECT COUNT(*) FROM survey_analyses WHERE id=?", (aid,)).fetchone()[0]
    conn.close()
    assert items == 0
    assert analyses == 1


# ── Descriptive ──────────────────────────────────────────────────

def test_descriptive_matches_fixture(client):
    c, db_path = client
    s = _seed(db_path)
    r = c.post(f"/surveys/{s['sid']}/analyses",
               json={"analysis_type": "descriptive", "data_source": "actual", "question_ids": s["qids"]},
               headers=s["headers"])
    assert r.status_code == 200
    items = {it["question_id"]: it for it in r.json()["results"][0]["items"]}
    q1, q4 = s["qids"][0], s["qids"][3]
    assert items[q1]["mean"] == pytest.approx(3.7, abs=0.001)
    assert items[q1]["sd"] == pytest.approx(1.16, abs=0.005)
    assert items[q4]["mean"] == pytest.approx(3.2, abs=0.001)  # reversed


# ── Reliability ──────────────────────────────────────────────────

def test_reliability_alpha_matches_fixture(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_construct(c, s, [s["qids"][0], s["qids"][2], s["qids"][3]]).json()["id"]
    r = c.post(f"/surveys/{s['sid']}/analyses",
               json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
               headers=s["headers"])
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["n"] == 10
    assert res["cronbach_alpha"] == pytest.approx(0.917, abs=0.001)
    by_q = {it["question_id"]: it for it in res["items"]}
    assert by_q[s["qids"][0]]["alpha_if_deleted"] == pytest.approx(0.867, abs=0.001)
    assert by_q[s["qids"][0]]["corrected_item_total_correlation"] == pytest.approx(0.851, abs=0.001)


def test_reliability_listwise_drops_missing(client):
    c, db_path = client
    s = _seed(db_path)
    # include q2 which has a missing at r10 -> listwise n=9, alpha 0.921
    cid = _mk_construct(c, s, s["qids"]).json()["id"]
    r = c.post(f"/surveys/{s['sid']}/analyses",
               json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
               headers=s["headers"])
    res = r.json()["results"][0]
    assert res["n"] == 9
    assert res["cronbach_alpha"] == pytest.approx(0.921, abs=0.001)


def test_reliability_needs_two_items_422(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_construct(c, s, [s["qids"][0]]).json()["id"]
    r = c.post(f"/surveys/{s['sid']}/analyses",
               json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
               headers=s["headers"])
    assert r.status_code == 422


# ── Normality ────────────────────────────────────────────────────

def test_normality_matches_scipy(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_construct(c, s, [s["qids"][0], s["qids"][2], s["qids"][3]]).json()["id"]
    r = c.post(f"/surveys/{s['sid']}/analyses",
               json={"analysis_type": "normality", "data_source": "actual", "construct_ids": [cid]},
               headers=s["headers"])
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["skewness"] == pytest.approx(-0.631, abs=0.001)
    assert res["kurtosis"] == pytest.approx(-1.22, abs=0.01)
    assert res["shapiro_w"] == pytest.approx(0.870, abs=0.005)
    assert "looks_normal" in res


# ── Persistence: result_json is a snapshot ───────────────────────

def test_analysis_result_is_snapshot(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_construct(c, s, [s["qids"][0], s["qids"][2], s["qids"][3]]).json()["id"]
    aid = c.post(f"/surveys/{s['sid']}/analyses",
                 json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
                 headers=s["headers"]).json()["id"]
    # mutate underlying answers
    conn = _conn(db_path)
    conn.execute("UPDATE survey_answers SET answer_value='1'")
    conn.commit(); conn.close()
    # GET returns stored snapshot, unchanged
    got = c.get(f"/analyses/{aid}", headers=s["headers"]).json()
    assert got["results"][0]["cronbach_alpha"] == pytest.approx(0.917, abs=0.001)


# ── APA table + docx export ──────────────────────────────────────

def test_apa_table_structure(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_construct(c, s, [s["qids"][0], s["qids"][2], s["qids"][3]]).json()["id"]
    res = c.post(f"/surveys/{s['sid']}/analyses",
                 json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
                 headers=s["headers"]).json()
    apa = res["apa_tables"][0]
    assert set(apa.keys()) == {"title", "columns", "rows", "note"}
    assert apa["columns"] and apa["rows"] and apa["note"]


def test_export_docx_roundtrip(client):
    from docx import Document
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_construct(c, s, [s["qids"][0], s["qids"][2], s["qids"][3]]).json()["id"]
    aid = c.post(f"/surveys/{s['sid']}/analyses",
                 json={"analysis_type": "descriptive", "data_source": "actual", "construct_ids": [cid]},
                 headers=s["headers"]).json()["id"]
    r = c.get(f"/analyses/{aid}/export/docx", headers=s["headers"])
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    doc = Document(io.BytesIO(r.content))
    assert len(doc.tables) >= 1


# ── Pro-gating + credits + source filter ─────────────────────────

def test_pro_gating_free_user_403(client):
    c, db_path = client
    s = _seed(db_path, tier="free")
    r = c.post(f"/surveys/{s['sid']}/constructs",
               json={"name": "X", "question_ids": [s["qids"][0], s["qids"][2]]}, headers=s["headers"])
    assert r.status_code == 403


def test_no_credit_deducted(client):
    c, db_path = client
    s = _seed(db_path)
    conn = _conn(db_path)
    before = conn.execute("SELECT kredit_remaining FROM users WHERE id=?", (s["uid"],)).fetchone()[0]
    conn.close()
    cid = _mk_construct(c, s, [s["qids"][0], s["qids"][2], s["qids"][3]]).json()["id"]
    c.post(f"/surveys/{s['sid']}/analyses",
           json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
           headers=s["headers"])
    conn = _conn(db_path)
    after = conn.execute("SELECT kredit_remaining FROM users WHERE id=?", (s["uid"],)).fetchone()[0]
    conn.close()
    assert before == after


def test_data_source_filter_pilot_vs_actual(client):
    c, db_path = client
    s = _seed(db_path)
    # add 3 pilot responses (all q's = 3) so pilot analysis differs & works
    conn = _conn(db_path)
    now = datetime.utcnow().isoformat()
    for r in range(3):
        rid = conn.execute("INSERT INTO survey_responses (survey_id, is_pilot, submitted_at, ip_hash) VALUES (?,1,?,?)",
                           (s["sid"], now, f"p{r}")).lastrowid
        for qid in s["qids"]:
            conn.execute("INSERT INTO survey_answers (response_id, question_id, answer_value) VALUES (?,?,'3')", (rid, qid))
    conn.commit(); conn.close()
    r_actual = c.post(f"/surveys/{s['sid']}/analyses",
                      json={"analysis_type": "descriptive", "data_source": "actual", "question_ids": [s["qids"][0]]},
                      headers=s["headers"]).json()
    r_pilot = c.post(f"/surveys/{s['sid']}/analyses",
                     json={"analysis_type": "descriptive", "data_source": "pilot", "question_ids": [s["qids"][0]]},
                     headers=s["headers"]).json()
    assert r_actual["results"][0]["items"][0]["n"] == 10
    assert r_pilot["results"][0]["items"][0]["n"] == 3
    assert r_pilot["results"][0]["items"][0]["mean"] == pytest.approx(3.0, abs=0.001)
