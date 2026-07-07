import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import sqlite3
import uuid
from datetime import datetime, date
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.database import init_db
from app.services.auth_service import create_jwt
from app.services.interpretation_guard import check_narrative, DISCLAIMER

# Fixture reuses the 36C-1 dataset: 4 likert-5 items (q4 reversed), 10 actual
# responses. Reliability of construct {q1,q3,q4} gives alpha 0.917, n=10, k=3
# (independently derived in test_survey_analysis.py).
Q1 = [4, 5, 3, 4, 2, 5, 3, 4, 2, 5]
Q2 = [4, 4, 3, 5, 2, 5, 4, 3, 3, None]
Q3 = [5, 4, 3, 4, 3, 5, 3, 4, 2, 4]
Q4 = [1, 2, 3, 1, 5, 2, 4, 3, 5, 2]

MOCK_PATH = "app.services.interpretation_guard.call_deepseek_raw"


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


def _seed(db_path, tier="pro", kredit=500):
    uid = str(uuid.uuid4())
    email = f"in_{uuid.uuid4().hex[:6]}@test.com"
    conn = _conn(db_path)
    conn.execute(
        """INSERT INTO users (id, email, tier, kredit_remaining, kredit_total, kredit_subscription,
           kredit_topup, tokens_used_internal, reset_date, created_at)
           VALUES (?,?,?,?,?,?,0,0,?,?)""",
        (uid, email, tier, kredit, kredit, kredit, _reset_date(), datetime.utcnow().isoformat()),
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
    for i, rev in enumerate([0, 0, 0, 1]):
        qid = conn.execute(
            """INSERT INTO survey_questions (section_id, question_text, question_type, options_json,
               likert_points, is_reversed, position) VALUES (?,?,?,?,?,?,?)""",
            (secid, f"Q{i+1}", "likert", json.dumps(["1", "2", "3", "4", "5"]), 5, rev, i),
        ).lastrowid
        qids.append(qid)
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


def _make_analysis(c, s):
    """Run a reliability analysis (alpha 0.917, n=10, k=3) and return its id."""
    cid = c.post(f"/surveys/{s['sid']}/constructs",
                 json={"name": "SAT", "question_ids": [s["qids"][0], s["qids"][2], s["qids"][3]]},
                 headers=s["headers"]).json()["id"]
    r = c.post(f"/surveys/{s['sid']}/analyses",
               json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
               headers=s["headers"])
    assert r.status_code == 200
    return r.json()["id"]


def _credits(db_path, uid):
    conn = _conn(db_path)
    v = conn.execute("SELECT kredit_remaining, kredit_subscription, kredit_topup FROM users WHERE id=?",
                     (uid,)).fetchone()
    conn.close()
    return v


# Narrative valid against the reliability result (alpha 0.917, n=10, k=3):
VALID_NARRATIVE = ("The SAT construct demonstrated excellent internal consistency, "
                   "Cronbach's alpha = 0.917, based on ten complete responses across three items.")
INVALID_NARRATIVE = ("The construct showed alpha = 0.917 and a significant improvement of 0.456 "
                     "over the benchmark.")  # 0.456 fabricated


# ═════════ Pure post-check tests (no LLM, no network) ═════════════

RESULT = {"t": -0.323, "p": 0.0239, "df": 28, "n": 30, "d": -0.118,
          "groups": [{"mean": 4.111, "sd": 0.412}, {"mean": 2.844, "sd": 0.452}]}


def test_postcheck_valid_number_variants():
    ok, off = check_narrative(
        "The difference was significant, t(28) = -0.32, p = .024 (also written 0.024), "
        "with means of 4.11 and 2.844 across 30 respondents.", RESULT)
    assert ok, off
    # 2dp vs 3dp rounding both accepted
    ok2, _ = check_narrative("d = -0.12 while sd = 0.45.", RESULT)
    assert ok2


def test_postcheck_single_foreign_number_rejected():
    ok, off = check_narrative("t(28) = -0.32, p = .043.", RESULT)  # .043 fabricated
    assert not ok
    assert any("043" in t for t in off)
    # fabricated integer is also rejected
    ok2, off2 = check_narrative("There were 7 groups.", RESULT)
    assert not ok2


def test_postcheck_p_below_001_format():
    tiny = {"t": 8.027, "p": 0.00000000968, "df": 28}
    ok, _ = check_narrative("The effect was significant, t(28) = 8.03, p < .001.", tiny)
    assert ok
    # p < .001 claimed but actual p is .024 -> reject
    ok2, off2 = check_narrative("t(28) = -0.32, p < .001.", RESULT)
    assert not ok2
    assert "p < .001" in off2


def test_postcheck_negative_and_integers():
    # unicode minus, ascii minus, magnitude mention, df/n integers
    ok, off = check_narrative(
        "t(28) = −0.32; a decline of 0.32 was observed among 30 participants (n = 30).", RESULT)
    assert ok, off
    ok2, _ = check_narrative("df was 29.", RESULT)  # 29 not in result
    assert not ok2


# ═════════ Endpoint tests (LLM mocked) ════════════════════════════

def test_interpret_success_saves_and_deducts(client):
    c, db_path = client
    s = _seed(db_path)
    aid = _make_analysis(c, s)
    before = _credits(db_path, s["uid"])
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE) as m:
        r = c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["kredit_used"] == 3
    assert VALID_NARRATIVE in body["narrative"]
    after = _credits(db_path, s["uid"])
    assert before["kredit_remaining"] - after["kredit_remaining"] == 3
    # deduction order: subscription first
    assert before["kredit_subscription"] - after["kredit_subscription"] == 3
    assert after["kredit_topup"] == before["kredit_topup"]
    # persisted + returned by GET
    got = c.get(f"/analyses/{aid}", headers=s["headers"]).json()
    assert got["interpretation"]["narrative"] == body["narrative"]
    assert m.await_count == 1


def test_interpret_invalid_twice_502_no_deduction(client):
    c, db_path = client
    s = _seed(db_path)
    aid = _make_analysis(c, s)
    before = _credits(db_path, s["uid"])
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=INVALID_NARRATIVE) as m:
        r = c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    assert r.status_code == 502
    assert "No credits were deducted" in r.json()["detail"]
    assert m.await_count == 2  # one retry with correction
    after = _credits(db_path, s["uid"])
    assert after["kredit_remaining"] == before["kredit_remaining"]
    got = c.get(f"/analyses/{aid}", headers=s["headers"]).json()
    assert "interpretation" not in got


def test_interpret_retry_then_valid(client):
    c, db_path = client
    s = _seed(db_path)
    aid = _make_analysis(c, s)
    before = _credits(db_path, s["uid"])
    with patch(MOCK_PATH, new_callable=AsyncMock,
               side_effect=[INVALID_NARRATIVE, VALID_NARRATIVE]) as m:
        r = c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    assert r.status_code == 200
    assert m.await_count == 2
    # correction instruction present in the retry prompt
    retry_prompt = m.await_args_list[1].args[0]
    assert "IMPORTANT CORRECTION" in retry_prompt
    after = _credits(db_path, s["uid"])
    assert before["kredit_remaining"] - after["kredit_remaining"] == 3  # deducted once


def test_insufficient_credits_402_no_llm_call(client):
    c, db_path = client
    s = _seed(db_path, kredit=2)
    aid = _make_analysis(c, s)
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE) as m:
        r = c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    assert r.status_code == 402
    assert m.await_count == 0


def test_regenerate_replaces_old(client):
    c, db_path = client
    s = _seed(db_path)
    aid = _make_analysis(c, s)
    second = "Reliability was excellent, alpha = 0.917 (three items, ten responses)."
    before = _credits(db_path, s["uid"])
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE):
        c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=second):
        r = c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    assert r.status_code == 200
    got = c.get(f"/analyses/{aid}", headers=s["headers"]).json()
    assert second in got["interpretation"]["narrative"]
    assert VALID_NARRATIVE not in got["interpretation"]["narrative"]
    after = _credits(db_path, s["uid"])
    assert before["kredit_remaining"] - after["kredit_remaining"] == 6  # 3 + 3


def test_disclaimer_appended_after_postcheck(client):
    c, db_path = client
    s = _seed(db_path)
    aid = _make_analysis(c, s)
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE):
        r = c.post(f"/analyses/{aid}/interpret", json={"language": "en"}, headers=s["headers"])
    narrative = r.json()["narrative"]
    assert narrative.endswith(DISCLAIMER["en"])
    assert VALID_NARRATIVE in narrative  # LLM output itself had no disclaimer
    # BM language gets the BM disclaimer
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE):
        r2 = c.post(f"/analyses/{aid}/interpret", json={"language": "ms"}, headers=s["headers"])
    assert r2.json()["narrative"].endswith(DISCLAIMER["ms"])


def test_language_param_overrides_project_default(client):
    c, db_path = client
    s = _seed(db_path)
    aid = _make_analysis(c, s)
    # project output_language defaults to 'bm' -> default prompt is Bahasa Melayu
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE) as m:
        c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    assert "Bahasa Melayu" in m.await_args.args[0]
    # explicit override to English wins
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE) as m2:
        c.post(f"/analyses/{aid}/interpret", json={"language": "en"}, headers=s["headers"])
    assert "academic English" in m2.await_args.args[0]
    # invalid language rejected
    r = c.post(f"/analyses/{aid}/interpret", json={"language": "fr"}, headers=s["headers"])
    assert r.status_code == 422


def test_interpretation_snapshot_after_mutation(client):
    c, db_path = client
    s = _seed(db_path)
    aid = _make_analysis(c, s)
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE):
        c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    conn = _conn(db_path)
    conn.execute("UPDATE survey_answers SET answer_value='1'")
    conn.commit(); conn.close()
    got = c.get(f"/analyses/{aid}", headers=s["headers"]).json()
    assert VALID_NARRATIVE in got["interpretation"]["narrative"]


def test_send_to_editor_reaches_chapter(client):
    """Send-to-Editor persists via the existing chapter content flow (the
    frontend Accept step ends in PATCH /chapters/{id}/content, same as chat)."""
    c, db_path = client
    s = _seed(db_path)
    aid = _make_analysis(c, s)
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE):
        c.post(f"/analyses/{aid}/interpret", json={}, headers=s["headers"])
    got = c.get(f"/analyses/{aid}", headers=s["headers"]).json()
    apa_sentence = got["results"][0]["apa_table"]["note"]
    narrative = got["interpretation"]["narrative"]
    chap = c.post(f"/projects/{s['pid']}/chapters",
                  json={"title": "Bab 4: Dapatan Kajian", "chapter_order": 4},
                  headers=s["headers"]).json()
    sent = f"{narrative}\n\n{apa_sentence}\n\n(See the accompanying APA table.)"
    r = c.patch(f"/projects/{s['pid']}/chapters/{chap['id']}/content",
                json={"content": sent}, headers=s["headers"])
    assert r.status_code == 200
    stored = c.get(f"/projects/{s['pid']}/chapters/{chap['id']}", headers=s["headers"]).json()
    assert narrative in stored["content"]


def test_pro_gating_and_ownership(client):
    c, db_path = client
    pro = _seed(db_path)
    aid = _make_analysis(c, pro)
    # free-tier owner -> 403
    free = _seed(db_path, tier="free")
    conn = _conn(db_path)
    # move the analysis's survey chain check: just call with free user's own survey
    conn.close()
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE) as m:
        # another user -> 404 (ownership)
        other = create_jwt({"user_id": str(uuid.uuid4()), "email": "x@test.com"})
        r = c.post(f"/analyses/{aid}/interpret", json={},
                   headers={"Authorization": f"Bearer {other}"})
        assert r.status_code == 404
        assert m.await_count == 0
    # free tier: seed analysis directly (constructs endpoint is pro-gated)
    conn = _conn(db_path)
    fsid = conn.execute("SELECT s.id FROM surveys s JOIN projects p ON p.id=s.project_id WHERE p.user_id=?",
                        (free["uid"],)).fetchone()["id"]
    fa = conn.execute(
        """INSERT INTO survey_analyses (survey_id, analysis_type, data_source, params_json, result_json, created_at)
           VALUES (?,?,?,?,?,?)""",
        (fsid, "reliability", "actual", "{}", json.dumps({"cronbach_alpha": 0.9}),
         datetime.utcnow().isoformat()),
    ).lastrowid
    conn.commit(); conn.close()
    with patch(MOCK_PATH, new_callable=AsyncMock, return_value=VALID_NARRATIVE) as m2:
        r2 = c.post(f"/analyses/{fa}/interpret", json={}, headers=free["headers"])
    assert r2.status_code == 403
    assert m2.await_count == 0
