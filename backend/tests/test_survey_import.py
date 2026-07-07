import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import io
import sqlite3
import uuid
from datetime import datetime, date
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import init_db
from app.services.auth_service import create_jwt
from app.services.survey_import import pii_suspected

# ── CSV fixture: same raw data as the 36C-1 reliability fixture ──
# q1 = [4,5,3,4,2,5,3,4,2,5]              mean 3.7
# q2 = [4,4,3,5,2,5,4,3,3,(missing)]      -> listwise drop of row 10
# q3 = [5,4,3,4,3,5,3,4,2,4]
# q4 = [1,2,3,1,5,2,4,3,5,2] RAW, imported with is_reversed=1
#      -> analysed 6-raw = [5,4,3,5,1,4,2,3,1,4], mean 3.2
# Independently computed (36C-1 derivation): construct {q1,q3,q4} n=10
# Cronbach alpha = 0.917; {q1,q2,q3,q4} listwise n=9 alpha = 0.921.
CSV_MAIN = """Email,Gender,q1,q2,q3,q4
a@x.com,Male,4,4,5,1
b@x.com,Male,5,4,4,2
c@x.com,Male,3,3,3,3
d@x.com,Male,4,5,4,1
e@x.com,Male,2,2,3,5
f@x.com,Female,5,5,5,2
g@x.com,Female,3,4,3,4
h@x.com,Female,4,3,4,3
i@x.com,Female,2,3,2,5
j@x.com,Female,5,,4,2
"""

MAPPINGS_MAIN = [
    {"column_name": "Email", "action": "skip"},
    {"column_name": "Gender", "action": "question", "question_type": "mcq"},
    {"column_name": "q1", "action": "question", "question_type": "likert", "likert_points": 5},
    {"column_name": "q2", "action": "question", "question_type": "likert", "likert_points": 5},
    {"column_name": "q3", "action": "question", "question_type": "likert", "likert_points": 5},
    {"column_name": "q4", "action": "question", "question_type": "likert", "likert_points": 5, "is_reversed": True},
]


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
    uid = str(uuid.uuid4())
    email = f"im_{uuid.uuid4().hex[:6]}@test.com"
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
    conn.commit(); conn.close()
    token = create_jwt({"user_id": uid, "email": email})
    return {"headers": {"Authorization": f"Bearer {token}"}, "uid": uid, "pid": pid, "db_path": db_path}


def _preview(c, s, content=CSV_MAIN, filename="gforms.csv"):
    return c.post(f"/projects/{s['pid']}/surveys/import/preview",
                  files={"file": (filename, content.encode() if isinstance(content, str) else content, "text/csv")},
                  headers=s["headers"])


def _confirm(c, s, token, mappings=None, **kw):
    body = {"preview_token": token, "survey_title": "Imported", "is_pilot": False,
            "column_mappings": mappings or MAPPINGS_MAIN, **kw}
    return c.post(f"/projects/{s['pid']}/surveys/import/confirm", json=body, headers=s["headers"])


def _import(c, s, **kw):
    p = _preview(c, s)
    assert p.status_code == 200, p.text
    r = _confirm(c, s, p.json()["preview_token"], **kw)
    assert r.status_code == 201, r.text
    return r.json()


# ── 1-2. Preview: CSV + XLSX ─────────────────────────────────────

def test_preview_csv(client):
    c, db_path = client
    s = _seed(db_path)
    r = _preview(c, s)
    assert r.status_code == 200
    j = r.json()
    assert j["row_count"] == 10
    assert [col["name"] for col in j["columns"]] == ["Email", "Gender", "q1", "q2", "q3", "q4"]
    assert len(j["sample_rows"]) == 5
    assert j["preview_token"]


def test_preview_xlsx_same_shape(client):
    import pandas as pd
    c, db_path = client
    s = _seed(db_path)
    df = pd.read_csv(io.StringIO(CSV_MAIN))
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    r = c.post(f"/projects/{s['pid']}/surveys/import/preview",
               files={"file": ("gforms.xlsx", buf.getvalue(),
                               "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
               headers=s["headers"])
    assert r.status_code == 200
    j = r.json()
    assert j["row_count"] == 10
    assert [col["name"] for col in j["columns"]] == ["Email", "Gender", "q1", "q2", "q3", "q4"]


# ── 3. Hard limits ───────────────────────────────────────────────

def test_limits_size_rows_cols(client):
    c, db_path = client
    s = _seed(db_path)
    # > 5MB -> 413
    big = b"a" * (5 * 1024 * 1024 + 1)
    assert _preview(c, s, content=big).status_code == 413
    # > 1000 rows -> 422 with the real count
    many = "v\n" + "\n".join(str(i) for i in range(1001))
    r = _preview(c, s, content=many)
    assert r.status_code == 422
    assert "1001" in r.json()["detail"]
    # > 60 columns -> 422
    wide = ",".join(f"c{i}" for i in range(61)) + "\n" + ",".join("1" for _ in range(61))
    r2 = _preview(c, s, content=wide)
    assert r2.status_code == 422
    assert "61" in r2.json()["detail"]
    # unsupported extension -> 422
    assert _preview(c, s, filename="data.txt").status_code == 422


# ── 4. PII heuristic ─────────────────────────────────────────────

def test_pii_heuristic_headers(client):
    for h in ("Email", "E-mel responden", "Nama", "Full Name", "No K/P", "IC No",
              "Telefon", "Phone", "No HP", "Alamat", "Address"):
        assert pii_suspected(h), h
    for h in ("q1", "Gender", "Faculty", "Skor", "Umur kumpulan"):
        assert not pii_suspected(h), h
    c, db_path = client
    s = _seed(db_path)
    cols = {col["name"]: col["pii_suspected"] for col in _preview(c, s).json()["columns"]}
    assert cols["Email"] is True
    assert cols["q1"] is False


# ── 5. PII override required ─────────────────────────────────────

def test_pii_column_requires_override(client):
    c, db_path = client
    s = _seed(db_path)
    tok = _preview(c, s).json()["preview_token"]
    bad = [{"column_name": "Email", "action": "question", "question_type": "open"},
           {"column_name": "q1", "action": "question", "question_type": "likert", "likert_points": 5}]
    r = _confirm(c, s, tok, mappings=bad)
    assert r.status_code == 422
    assert "Email" in r.json()["detail"] and "personal data" in r.json()["detail"]
    # explicit override passes (same token still valid — validation must not burn it)
    ok = [{"column_name": "Email", "action": "question", "question_type": "open", "override_pii_warning": True},
          {"column_name": "q1", "action": "question", "question_type": "likert", "likert_points": 5}]
    r2 = _confirm(c, s, tok, mappings=ok)
    assert r2.status_code == 201


# ── 6-7. Mapping validation ──────────────────────────────────────

def test_mcq_too_many_unique_422(client):
    c, db_path = client
    s = _seed(db_path)
    csv = "answer\n" + "\n".join(f"unique text {i}" for i in range(13))
    tok = _preview(c, s, content=csv).json()["preview_token"]
    r = _confirm(c, s, tok, mappings=[{"column_name": "answer", "action": "question", "question_type": "mcq"}])
    assert r.status_code == 422
    assert "distinct values" in r.json()["detail"]


def test_likert_points_required_and_out_of_range_becomes_missing(client):
    c, db_path = client
    s = _seed(db_path)
    tok = _preview(c, s).json()["preview_token"]
    r = _confirm(c, s, tok, mappings=[{"column_name": "q1", "action": "question", "question_type": "likert"}])
    assert r.status_code == 422
    # out-of-scale values -> missing rows for that column, import still succeeds
    csv = "score\n1\n2\n9\n3\nx\n"
    tok2 = _preview(c, s, content=csv).json()["preview_token"]
    r2 = _confirm(c, s, tok2, mappings=[{"column_name": "score", "action": "question",
                                         "question_type": "likert", "likert_points": 5}])
    assert r2.status_code == 201
    j = r2.json()
    conn = _conn(db_path)
    vals = [row["answer_value"] for row in conn.execute(
        """SELECT a.answer_value FROM survey_answers a
           JOIN survey_responses r ON r.id = a.response_id WHERE r.survey_id=?""",
        (j["survey_id"],)).fetchall()]
    conn.close()
    assert sorted(vals) == ["1", "2", "3"]  # 9 and 'x' became missing, not stored


# ── 8-10. Imported survey shape ──────────────────────────────────

def test_imported_status_and_metadata(client):
    c, db_path = client
    s = _seed(db_path)
    j = _import(c, s)
    assert j["question_count"] == 5 and j["imported_responses"] == 10
    survey = c.get(f"/surveys/{j['survey_id']}", headers=s["headers"]).json()
    assert survey["status"] == "imported"
    assert survey["import_filename"] == "gforms.csv"
    assert survey["imported_row_count"] == 10
    assert survey["imported_at"]
    # one section, questions in file column order, q4 reversed, mcq options derived
    assert len(survey["sections"]) == 1
    qs = survey["sections"][0]["questions"]
    assert [q["question_text"] for q in qs] == ["Gender", "q1", "q2", "q3", "q4"]
    assert qs[0]["question_type"] == "mcq" and qs[0]["options"] == ["Female", "Male"]
    assert qs[4]["is_reversed"] is True


def test_is_pilot_applied_to_all_rows(client):
    c, db_path = client
    s = _seed(db_path)
    j = _import(c, s, is_pilot=True)
    conn = _conn(db_path)
    flags = {row["is_pilot"] for row in conn.execute(
        "SELECT is_pilot FROM survey_responses WHERE survey_id=?", (j["survey_id"],)).fetchall()}
    conn.close()
    assert flags == {1}


def test_ip_hash_synthetic_and_unique(client):
    c, db_path = client
    s = _seed(db_path)
    j = _import(c, s)
    conn = _conn(db_path)
    hashes = [row["ip_hash"] for row in conn.execute(
        "SELECT ip_hash FROM survey_responses WHERE survey_id=?", (j["survey_id"],)).fetchall()]
    conn.close()
    assert len(hashes) == 10
    assert len(set(hashes)) == 10  # no collisions
    assert all(len(h) == 64 for h in hashes)  # sha256 hex, not a raw IP


# ── 11-12. Locked forever ────────────────────────────────────────

def test_structure_edit_on_imported_409(client):
    c, db_path = client
    s = _seed(db_path)
    j = _import(c, s)
    survey = c.get(f"/surveys/{j['survey_id']}", headers=s["headers"]).json()
    r = c.post(f"/surveys/{j['survey_id']}/sections", json={"title": "New"}, headers=s["headers"])
    assert r.status_code == 409
    qid = survey["sections"][0]["questions"][0]["id"]
    assert c.patch(f"/questions/{qid}", json={"question_text": "x"}, headers=s["headers"]).status_code == 409
    assert c.delete(f"/questions/{qid}", headers=s["headers"]).status_code == 409


def test_publish_lifecycle_on_imported_403(client):
    c, db_path = client
    s = _seed(db_path)
    j = _import(c, s)
    sid = j["survey_id"]
    for path, body in (("publish", {"mode": "pilot"}), ("close", None), ("reopen", None),
                       ("unlock", None), ("unpublish", None)):
        r = c.post(f"/surveys/{sid}/{path}", json=body, headers=s["headers"]) if body \
            else c.post(f"/surveys/{sid}/{path}", headers=s["headers"])
        assert r.status_code == 403, path
        assert "Not applicable" in r.json()["detail"], path


# ── 13. Real integration with the analysis engine ────────────────

def test_imported_survey_full_analysis_pipeline(client):
    """No mocks: constructs + descriptive + reliability run on imported data
    and reproduce the independently-derived 36C-1 values."""
    c, db_path = client
    s = _seed(db_path)
    j = _import(c, s)
    sid = j["survey_id"]
    survey = c.get(f"/surveys/{sid}", headers=s["headers"]).json()
    q = {qq["question_text"]: qq["id"] for qq in survey["sections"][0]["questions"]}
    # construct {q1,q3,q4}: independent value alpha = 0.917 (q4 reverse-coded)
    cid = c.post(f"/surveys/{sid}/constructs",
                 json={"name": "SAT", "question_ids": [q["q1"], q["q3"], q["q4"]]},
                 headers=s["headers"]).json()["id"]
    rel = c.post(f"/surveys/{sid}/analyses",
                 json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid]},
                 headers=s["headers"])
    assert rel.status_code == 200
    res = rel.json()["results"][0]
    assert res["n"] == 10
    assert res["cronbach_alpha"] == pytest.approx(0.917, abs=0.001)
    # descriptive: q1 mean 3.7, q4 reversed mean 3.2; q2 has 1 missing
    desc = c.post(f"/surveys/{sid}/analyses",
                  json={"analysis_type": "descriptive", "data_source": "actual",
                        "question_ids": [q["q1"], q["q2"], q["q4"]]},
                  headers=s["headers"]).json()
    items = {it["question_id"]: it for it in desc["results"][0]["items"]}
    assert items[q["q1"]]["mean"] == pytest.approx(3.7, abs=0.001)
    assert items[q["q4"]]["mean"] == pytest.approx(3.2, abs=0.001)  # reverse-coding applied
    assert items[q["q2"]]["n"] == 9 and items[q["q2"]]["missing"] == 1
    # listwise 4-item construct: independent value alpha = 0.921, n=9
    cid4 = c.post(f"/surveys/{sid}/constructs",
                  json={"name": "ALL", "question_ids": [q["q1"], q["q2"], q["q3"], q["q4"]]},
                  headers=s["headers"]).json()["id"]
    rel4 = c.post(f"/surveys/{sid}/analyses",
                  json={"analysis_type": "reliability", "data_source": "actual", "construct_ids": [cid4]},
                  headers=s["headers"]).json()["results"][0]
    assert rel4["n"] == 9
    assert rel4["cronbach_alpha"] == pytest.approx(0.921, abs=0.001)


# ── 14. Rate limit ───────────────────────────────────────────────

def test_import_rate_limit_daily(client):
    c, db_path = client
    s = _seed(db_path)
    for i in range(10):
        assert _preview(c, s).status_code == 200, f"preview {i+1}"
    r = _preview(c, s)
    assert r.status_code == 429


# ── 15. Preview token TTL / invalid ──────────────────────────────

def test_preview_token_expired_or_missing_410(client):
    c, db_path = client
    s = _seed(db_path)
    r = _confirm(c, s, "nonexistent-token")
    assert r.status_code == 410
    # expired token purged
    from app.services import survey_import as si
    from datetime import timedelta
    tok = _preview(c, s).json()["preview_token"]
    si._PREVIEW_CACHE[tok]["expires"] = datetime.utcnow() - timedelta(minutes=1)
    r2 = _confirm(c, s, tok)
    assert r2.status_code == 410


# ── 16. Pro-gating + ownership ───────────────────────────────────

def test_pro_gating_and_ownership(client):
    c, db_path = client
    free = _seed(db_path, tier="free")
    assert _preview(c, free).status_code == 403
    pro = _seed(db_path)
    tok = _preview(c, pro).json()["preview_token"]
    # another user cannot confirm into someone else's project
    other = _seed(db_path)
    r = c.post(f"/projects/{pro['pid']}/surveys/import/confirm",
               json={"preview_token": tok, "is_pilot": False, "column_mappings": MAPPINGS_MAIN},
               headers=other["headers"])
    assert r.status_code == 404
