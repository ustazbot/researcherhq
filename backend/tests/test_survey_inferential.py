import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import json
import sqlite3
import uuid
from datetime import datetime, date
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import init_db
from app.services.auth_service import create_jwt

# ═════════════════════════════════════════════════════════════════
# Fixture: 30 respondents (r1-r15 Male, r16-r30 Female), all actual.
#
# Questions:
#   g   mcq  Gender  [Male, Female]        -> 15 M / 15 F
#   f   demographic Faculty [FA, FB, FC]   -> M: FA×7 FB×5 FC×3 ; F: FA×3 FB×5 FC×7
#   s1  likert-5
#   s2  likert-5
#   s3  likert-5 is_reversed=1 (analysed value = 6 − raw)
#   m1  likert-5 (r30 MISSING -> listwise/pairwise tests)
#   e1  likert-5 (engineered unequal variance by gender -> Welch trigger)
#   qx  mcq [X, Y, Z]                      -> X×15 / Y×14 / Z×1 (Z excluded, n<2)
#   qy  mcq [P, Q]                         -> P×29 / Q×1 (after exclusion only 1 group -> 422)
#
# SAT construct = {s1, s2, s3}; composite = rowwise mean of reversed frame.
#
# ALL expected values below were computed INDEPENDENTLY with numpy/scipy
# directly on these raw lists (not via the app engine). Derivation:
#   s3 analysed = 6 − raw
#   sat = (s1 + s2 + s3_analysed) / 3
#   SAT by gender: M mean 4.1111 sd 0.4115 | F mean 2.8444 sd 0.4519
#
# [T-IND SAT×gender]  levene W=0.0446 p=.8343 (pooled path)
#   scipy.ttest_ind: t=8.0267 df=28 p=9.68e-09
#   pooled sp = sqrt(((14)(.4115²)+(14)(.4519²))/28); d=(4.1111−2.8444)/sp = 2.9309
# [T-IND m1×gender]   n=15/14 (r30 missing) levene p=.8974
#   t=4.4738 df=27 p=1.252e-04 d=1.6625 ; means 3.9333 / 2.9286
# [WELCH e1×gender]   levene W=33.3529 p=3.36e-06 -> Welch applied
#   scipy.ttest_ind(equal_var=False): t=−0.3232 df=15.6543 p=.7508 ; d(pooled)=−0.1180
# [T-PAIR SAT vs m1]  pairs listwise n=29 (r30 dropped)
#   scipy.ttest_rel: t=0.4959 df=28 p=.6238 ; d = mean(diff)/sd(diff) = 0.0921
# [ANOVA SAT×faculty] groups 10/10/10
#   scipy.f_oneway: F=0.9155 df=(2,27) p=.4124
#   eta² = SS_between/SS_total = 0.0635
#   tukey_hsd p: FA-FB .8330 | FA-FC .3815 | FB-FC .7239
#   mean diffs: FA-FB 0.2000 | FA-FC 0.4667 | FB-FC 0.2667
# [MW e1×gender]      scipy.mannwhitneyu two-sided: U=105.0 p=.7553
#   z = |norm.isf(p/2)| = 0.3117 ; r = z/√30 = 0.0569
# [KW SAT×faculty]    scipy.kruskal: H=1.9598 df=2 p=.3754
# [WX SAT vs m1]      scipy.wilcoxon (n=29): W=141.5 p=.8071
#   z = |norm.isf(p/2)| = 0.2442 ; r = z/√29 = 0.0454
# [CORR] pairwise deletion:
#   SAT-m1 n=29: pearson r=0.6771 p=5.49e-05 (***) | spearman rho=0.7036 p=2.06e-05
#   SAT-e1 n=30: pearson r=0.0286 p=.8808 (ns)     | spearman rho=0.0185
#   m1-e1  n=29: pearson r=−0.0999 p=.6061 (ns)
# [CHI gender×faculty] observed [[7,5,3],[3,5,7]], no Yates correction
#   chi2=3.2000 df=2 p=.2019 ; V = sqrt(3.2/(30·1)) = 0.3266 ; expected all 5 (no warning)
# [CHI gender×qx]      observed [[15,0,0],[0,14,1]]
#   chi2=30.0 df=2 p=3.06e-07 V=1.0 ; 2/6 expected cells <5 (33%>20% -> warning)
# [NORMALITY for wizard] looks_normal = |skew|<1 & |kurt|<1 & shapiro p>.05
#   SAT M: skew −0.2142 kurt −0.7825 W .9251 p .2299 -> normal
#   SAT F: skew 0.0182 kurt −0.3966 W .9550 p .6061 -> normal
#   SAT FA/FB/FC: all normal (p .5574/.5605/.0962; |skew|,|kurt|<1)
#   e1 M: kurt 7.0 shapiro p 6.3e-06 -> NOT normal ; e1 F: kurt −1.548 -> NOT normal
# ═════════════════════════════════════════════════════════════════

GENDER = ["Male"] * 15 + ["Female"] * 15
FACULTY = ["FA"]*7 + ["FB"]*5 + ["FC"]*3 + ["FA"]*3 + ["FB"]*5 + ["FC"]*7
S1 = [4,5,3,4,5,4,3,5,4,4,5,3,4,4,5] + [3,2,4,3,2,3,4,2,3,3,2,4,3,3,2]
S2 = [4,4,5,3,4,5,4,4,4,5,4,4,5,3,4] + [2,3,3,4,2,3,3,2,4,3,3,2,3,4,3]
S3_RAW = [2,1,2,3,1,2,2,1,3,2,2,1,2,2,3] + [3,4,3,2,4,3,4,3,3,4,3,3,4,3,3]
M1 = [4,4,3,4,5,4,3,4,4,5,4,3,4,4,4] + [3,3,4,2,3,3,3,2,4,3,3,3,2,3,None]
E1 = [3,3,3,3,3,3,3,3,3,3,3,3,3,2,4] + [1,5,2,4,1,5,3,2,4,5,1,3,5,2,4]
QX = ["X"]*15 + ["Y"]*14 + ["Z"]
QY = ["P"]*29 + ["Q"]


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


def _seed(db_path, tier="pro", with_pilot=False):
    """Seed user+project+survey with the 30-respondent inferential fixture."""
    uid = str(uuid.uuid4())
    email = f"inf_{uuid.uuid4().hex[:6]}@test.com"
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

    def q(text, qtype, options=None, points=None, reversed_=0, pos=0):
        return conn.execute(
            """INSERT INTO survey_questions (section_id, question_text, question_type, options_json,
               likert_points, is_reversed, position) VALUES (?,?,?,?,?,?,?)""",
            (secid, text, qtype, json.dumps(options) if options else None, points, reversed_, pos),
        ).lastrowid

    ids = {
        "g": q("Gender", "mcq", ["Male", "Female"], pos=0),
        "f": q("Faculty", "demographic", ["FA", "FB", "FC"], pos=1),
        "s1": q("S1", "likert", ["1","2","3","4","5"], 5, 0, 2),
        "s2": q("S2", "likert", ["1","2","3","4","5"], 5, 0, 3),
        "s3": q("S3", "likert", ["1","2","3","4","5"], 5, 1, 4),  # reversed
        "m1": q("M1", "likert", ["1","2","3","4","5"], 5, 0, 5),
        "e1": q("E1", "likert", ["1","2","3","4","5"], 5, 0, 6),
        "qx": q("QX", "mcq", ["X", "Y", "Z"], pos=7),
        "qy": q("QY", "mcq", ["P", "Q"], pos=8),
    }
    cols = [("g", GENDER), ("f", FACULTY), ("s1", S1), ("s2", S2), ("s3", S3_RAW),
            ("m1", M1), ("e1", E1), ("qx", QX), ("qy", QY)]
    for r in range(30):
        rid = conn.execute(
            "INSERT INTO survey_responses (survey_id, is_pilot, submitted_at, ip_hash) VALUES (?,0,?,?)",
            (sid, now, f"hash{r}"),
        ).lastrowid
        for key, vals in cols:
            v = vals[r]
            if v is None:
                continue
            conn.execute("INSERT INTO survey_answers (response_id, question_id, answer_value) VALUES (?,?,?)",
                         (rid, ids[key], str(v)))
    if with_pilot:
        # 4 pilot responses: gender 2M/2F, sat items varied
        pilot_rows = [("Male", 4, 3, 2), ("Male", 5, 4, 1), ("Female", 2, 3, 4), ("Female", 3, 2, 3)]
        for i, (gv, v1, v2, v3) in enumerate(pilot_rows):
            rid = conn.execute(
                "INSERT INTO survey_responses (survey_id, is_pilot, submitted_at, ip_hash) VALUES (?,1,?,?)",
                (sid, now, f"pilot{i}"),
            ).lastrowid
            for key, v in (("g", gv), ("s1", v1), ("s2", v2), ("s3", v3)):
                conn.execute("INSERT INTO survey_answers (response_id, question_id, answer_value) VALUES (?,?,?)",
                             (rid, ids[key], str(v)))
    conn.commit()
    conn.close()
    token = create_jwt({"user_id": uid, "email": email})
    return {"headers": {"Authorization": f"Bearer {token}"}, "sid": sid, "ids": ids,
            "uid": uid, "db_path": db_path, "pid": pid}


def _mk_sat(c, s):
    """Create SAT construct {s1, s2, s3}."""
    r = c.post(f"/surveys/{s['sid']}/constructs",
               json={"name": "SAT", "question_ids": [s["ids"]["s1"], s["ids"]["s2"], s["ids"]["s3"]]},
               headers=s["headers"])
    assert r.status_code == 201
    return r.json()["id"]


def _run(c, s, body):
    return c.post(f"/surveys/{s['sid']}/analyses", json={"data_source": "actual", **body}, headers=s["headers"])


# ── 1. Independent t-test matches independent computation ────────

def test_ttest_independent_matches_fixture(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    r = _run(c, s, {"analysis_type": "ttest_independent",
                    "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["g"]})
    assert r.status_code == 200
    res = r.json()["results"][0]
    # independent: t=8.0267 df=28 p=9.68e-09 d=2.9309, pooled (levene p=.8343)
    assert res["welch_applied"] is False
    assert res["statistic"] == pytest.approx(8.027, abs=0.001)
    assert res["df"] == pytest.approx(28, abs=0.001)
    assert res["p"] < 0.001
    assert res["effect_size"]["name"] == "Cohen's d"
    assert res["effect_size"]["value"] == pytest.approx(2.931, abs=0.001)
    assert res["effect_size"]["band"] == "large"
    groups = {g["group"]: g for g in res["groups"]}
    assert groups["Male"]["mean"] == pytest.approx(4.111, abs=0.001)
    assert groups["Female"]["mean"] == pytest.approx(2.844, abs=0.001)
    assert res["assumption_checks"]["levene"]["p"] == pytest.approx(0.834, abs=0.001)


# ── 2. Welch auto-applied when Levene p < .05 ────────────────────

def test_welch_applied_when_levene_significant(client):
    c, db_path = client
    s = _seed(db_path)
    r = _run(c, s, {"analysis_type": "ttest_independent",
                    "outcome": {"question_id": s["ids"]["e1"]}, "grouping_question_id": s["ids"]["g"]})
    assert r.status_code == 200
    res = r.json()["results"][0]
    # independent: levene p=3.36e-06 -> Welch t=-0.3232 df=15.6543 p=.7508 d(pooled)=-0.1180
    assert res["welch_applied"] is True
    assert res["assumption_checks"]["levene"]["p"] < 0.05
    assert res["statistic"] == pytest.approx(-0.323, abs=0.001)
    assert res["df"] == pytest.approx(15.654, abs=0.001)
    assert res["p"] == pytest.approx(0.7508, abs=0.001)
    assert res["effect_size"]["value"] == pytest.approx(-0.118, abs=0.001)
    assert "Welch" in res["apa_table"]["note"]
    assert "t(15.65)" in res["apa_sentence"]  # Welch df formatted with 2 decimals


# ── 3. Paired t-test: listwise pairing + d from SD of differences ─

def test_ttest_paired_listwise_and_d(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    r = _run(c, s, {"analysis_type": "ttest_paired",
                    "outcome": {"construct_id": cid}, "outcome2": {"question_id": s["ids"]["m1"]}})
    assert r.status_code == 200
    res = r.json()["results"][0]
    # independent: n=29 (r30 m1 missing), t=0.4959 df=28 p=.6238 d=0.0921
    assert res["n_pairs"] == 29
    assert res["statistic"] == pytest.approx(0.496, abs=0.001)
    assert res["df"] == 28
    assert res["p"] == pytest.approx(0.6238, abs=0.001)
    assert res["effect_size"]["value"] == pytest.approx(0.092, abs=0.001)


# ── 4. ANOVA: F/df/p/eta² + Tukey pairs vs scipy direct ──────────

def test_anova_matches_fixture_and_tukey(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    r = _run(c, s, {"analysis_type": "anova_oneway",
                    "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["f"]})
    assert r.status_code == 200
    res = r.json()["results"][0]
    # independent: F=0.9155 (2,27) p=.4124 eta²=.0635
    assert res["statistic"] == pytest.approx(0.9155, abs=0.001)
    assert res["df_between"] == 2 and res["df_within"] == 27
    assert res["p"] == pytest.approx(0.4124, abs=0.001)
    assert res["effect_size"]["name"] == "eta-squared"
    assert res["effect_size"]["value"] == pytest.approx(0.064, abs=0.001)
    # Tukey pairs: FA-FB p=.8330 diff .2000 | FA-FC p=.3815 diff .4667 | FB-FC p=.7239
    pairs = {(p["group_a"], p["group_b"]): p for p in res["posthoc"]}
    assert pairs[("FA", "FB")]["p"] == pytest.approx(0.8330, abs=0.001)
    assert pairs[("FA", "FB")]["mean_diff"] == pytest.approx(0.200, abs=0.001)
    assert pairs[("FA", "FC")]["p"] == pytest.approx(0.3815, abs=0.001)
    assert pairs[("FA", "FC")]["mean_diff"] == pytest.approx(0.467, abs=0.001)
    assert pairs[("FB", "FC")]["p"] == pytest.approx(0.7239, abs=0.001)
    # post-hoc rendered as its own APA table
    titles = [t["title"] for t in r.json()["apa_tables"]]
    assert any("Tukey" in t for t in titles)


# ── 5. Non-parametric trio matches independent computation ───────

def test_mann_whitney_matches(client):
    c, db_path = client
    s = _seed(db_path)
    r = _run(c, s, {"analysis_type": "mann_whitney",
                    "outcome": {"question_id": s["ids"]["e1"]}, "grouping_question_id": s["ids"]["g"]})
    res = r.json()["results"][0]
    # independent: U=105.0 p=.7553 z=.3117 r=z/√30=.0569
    assert res["statistic"] == pytest.approx(105.0, abs=0.1)
    assert res["p"] == pytest.approx(0.7553, abs=0.001)
    assert res["effect_size"]["name"] == "r"
    assert res["effect_size"]["value"] == pytest.approx(0.057, abs=0.001)


def test_kruskal_wallis_matches(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    r = _run(c, s, {"analysis_type": "kruskal_wallis",
                    "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["f"]})
    res = r.json()["results"][0]
    # independent: H=1.9598 df=2 p=.3754
    assert res["statistic"] == pytest.approx(1.960, abs=0.001)
    assert res["df"] == 2
    assert res["p"] == pytest.approx(0.3754, abs=0.001)


def test_wilcoxon_matches(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    r = _run(c, s, {"analysis_type": "wilcoxon",
                    "outcome": {"construct_id": cid}, "outcome2": {"question_id": s["ids"]["m1"]}})
    res = r.json()["results"][0]
    # independent: W=141.5 p=.8071 z=.2442 r=z/√29=.0454, n=29 pairs
    assert res["n_pairs"] == 29
    assert res["statistic"] == pytest.approx(141.5, abs=0.1)
    assert res["p"] == pytest.approx(0.8071, abs=0.001)
    assert res["effect_size"]["value"] == pytest.approx(0.045, abs=0.001)


# ── 6. Correlation matrix: Pearson + Spearman + markers ──────────

def test_correlation_matrix_matches(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    r = _run(c, s, {"analysis_type": "correlation",
                    "variables": [{"construct_id": cid}, {"question_id": s["ids"]["m1"]},
                                  {"question_id": s["ids"]["e1"]}]})
    assert r.status_code == 200
    res = r.json()["results"][0]
    pairs = {(p["variable_a"], p["variable_b"]): p for p in res["pairs"]}
    sat_m1 = pairs[("SAT", f"Q{s['ids']['m1']}")]
    # independent: SAT-m1 n=29 pearson r=.6771 p=5.49e-05 | spearman rho=.7036
    assert sat_m1["n"] == 29  # pairwise deletion (r30 m1 missing)
    assert sat_m1["pearson_r"] == pytest.approx(0.677, abs=0.001)
    assert sat_m1["spearman_rho"] == pytest.approx(0.704, abs=0.001)
    sat_e1 = pairs[("SAT", f"Q{s['ids']['e1']}")]
    assert sat_e1["n"] == 30
    assert sat_e1["pearson_r"] == pytest.approx(0.029, abs=0.001)
    # significance markers in the matrix: SAT-m1 p=5.5e-05 -> ***, SAT-e1 ns -> none
    tables = r.json()["apa_tables"]
    pearson_table = next(t for t in tables if t["title"].startswith("Pearson"))
    flat = " | ".join(str(cell) for row in pearson_table["rows"] for cell in row)
    assert "0.677***" in flat
    assert "0.029*" not in flat
    # both matrices exported
    assert any(t["title"].startswith("Spearman") for t in tables)


# ── 7. Chi-square + Cramér's V + low-expected warning ────────────

def test_chi_square_matches(client):
    c, db_path = client
    s = _seed(db_path)
    r = _run(c, s, {"analysis_type": "chi_square",
                    "question_ids": [s["ids"]["g"], s["ids"]["f"]]})
    assert r.status_code == 200
    res = r.json()["results"][0]
    # independent: chi2=3.2 df=2 p=.2019 V=.3266 (expected all 5 -> no warning)
    assert res["statistic"] == pytest.approx(3.200, abs=0.001)
    assert res["df"] == 2
    assert res["p"] == pytest.approx(0.2019, abs=0.001)
    assert res["effect_size"]["name"] == "Cramér's V"
    assert res["effect_size"]["value"] == pytest.approx(0.327, abs=0.001)
    assert res["warning"] is None


def test_chi_square_low_expected_warning(client):
    c, db_path = client
    s = _seed(db_path)
    r = _run(c, s, {"analysis_type": "chi_square",
                    "question_ids": [s["ids"]["g"], s["ids"]["qx"]]})
    res = r.json()["results"][0]
    # independent: chi2=30.0 df=2 p=3.06e-07 V=1.0; 33% of cells expected<5 -> warning
    assert res["statistic"] == pytest.approx(30.0, abs=0.001)
    assert res["effect_size"]["value"] == pytest.approx(1.0, abs=0.001)
    assert res["warning"] is not None and "expected" in res["warning"]


# ── 8. Group exclusion (n<2) reported; remaining <2 -> 422 ───────

def test_small_group_excluded_and_reported(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    # qx: X×15 / Y×14 / Z×1 -> Z excluded, t-test runs on X vs Y
    r = _run(c, s, {"analysis_type": "ttest_independent",
                    "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["qx"]})
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["excluded_groups"] == [{"group": "Z", "n": 1}]
    assert {g["group"] for g in res["groups"]} == {"X", "Y"}


def test_remaining_groups_below_two_422(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    # qy: P×29 / Q×1 -> Q excluded, only 1 group left
    r = _run(c, s, {"analysis_type": "ttest_independent",
                    "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["qy"]})
    assert r.status_code == 422


# ── 9. Grouping question must be mcq/demographic ─────────────────

def test_likert_grouping_rejected_422(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    r = _run(c, s, {"analysis_type": "ttest_independent",
                    "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["m1"]})
    assert r.status_code == 422
    assert "MCQ or demographic" in r.json()["detail"]


# ── 10. APA sentence formatting ──────────────────────────────────

def test_apa_sentence_formats(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    # p = 9.68e-09 -> "p < .001"; pooled df integer -> "t(28)"
    r = _run(c, s, {"analysis_type": "ttest_independent",
                    "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["g"]})
    sent = r.json()["results"][0]["apa_sentence"]
    assert "p < .001" in sent
    assert "t(28)" in sent
    assert "d = 2.93" in sent
    # non-significant p rendered as "p = .xxx" without leading zero (ANOVA p=.4124)
    r2 = _run(c, s, {"analysis_type": "anova_oneway",
                     "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["f"]})
    sent2 = r2.json()["results"][0]["apa_sentence"]
    assert "p = .412" in sent2
    assert "F(2, 27)" in sent2


# ── 11. Wizard decision tree ─────────────────────────────────────

def _wizard(c, s, body):
    return c.post(f"/surveys/{s['sid']}/wizard", json={"data_source": "actual", **body}, headers=s["headers"])


def test_wizard_two_groups_normal_suggests_ttest(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    # SAT per gender: both groups looks_normal -> ttest_independent, alt mann_whitney
    r = _wizard(c, s, {"goal": "compare_groups", "outcome": {"construct_id": cid},
                       "grouping_question_id": s["ids"]["g"]})
    assert r.status_code == 200
    j = r.json()
    assert j["suggested_test"] == "ttest_independent"
    assert j["alternative_test"] == "mann_whitney"
    assert j["justification"]
    assert {g["group"] for g in j["group_summary"]} == {"Male", "Female"}


def test_wizard_three_groups_normal_suggests_anova(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    # SAT per faculty: FA/FB/FC all looks_normal -> anova_oneway, alt kruskal_wallis
    r = _wizard(c, s, {"goal": "compare_groups", "outcome": {"construct_id": cid},
                       "grouping_question_id": s["ids"]["f"]})
    j = r.json()
    assert j["suggested_test"] == "anova_oneway"
    assert j["alternative_test"] == "kruskal_wallis"


def test_wizard_nonnormal_suggests_nonparametric(client):
    c, db_path = client
    s = _seed(db_path)
    # e1 per gender: both groups NOT looks_normal -> mann_whitney, alt ttest_independent
    r = _wizard(c, s, {"goal": "compare_groups", "outcome": {"question_id": s["ids"]["e1"]},
                       "grouping_question_id": s["ids"]["g"]})
    j = r.json()
    assert j["suggested_test"] == "mann_whitney"
    assert j["alternative_test"] == "ttest_independent"


def test_wizard_paired_and_other_goals(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    # paired + SAT normal overall? SAT all: looks_normal False (kurt -1.067) -> wilcoxon
    r = _wizard(c, s, {"goal": "compare_groups", "paired": True, "outcome": {"construct_id": cid}})
    assert r.json()["suggested_test"] == "wilcoxon"
    # relationship -> correlation
    r2 = _wizard(c, s, {"goal": "relationship", "outcome": {"construct_id": cid}})
    assert r2.json()["suggested_test"] == "correlation"
    # association_categorical -> chi_square
    r3 = _wizard(c, s, {"goal": "association_categorical", "outcome": {"question_id": s["ids"]["g"]},
                        "grouping_question_id": s["ids"]["f"]})
    assert r3.json()["suggested_test"] == "chi_square"


# ── 12. Wizard: no credit deduction, nothing saved ───────────────

def test_wizard_no_credit_no_save(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    conn = _conn(db_path)
    before = conn.execute("SELECT kredit_remaining FROM users WHERE id=?", (s["uid"],)).fetchone()[0]
    conn.close()
    _wizard(c, s, {"goal": "compare_groups", "outcome": {"construct_id": cid},
                   "grouping_question_id": s["ids"]["g"]})
    conn = _conn(db_path)
    after = conn.execute("SELECT kredit_remaining FROM users WHERE id=?", (s["uid"],)).fetchone()[0]
    saved = conn.execute("SELECT COUNT(*) FROM survey_analyses").fetchone()[0]
    conn.close()
    assert before == after
    assert saved == 0


# ── 13. Snapshot persistence for new types ───────────────────────

def test_snapshot_persistence_new_types(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    aid = _run(c, s, {"analysis_type": "ttest_independent",
                      "outcome": {"construct_id": cid},
                      "grouping_question_id": s["ids"]["g"]}).json()["id"]
    conn = _conn(db_path)
    conn.execute("UPDATE survey_answers SET answer_value='1'")
    conn.commit(); conn.close()
    got = c.get(f"/analyses/{aid}", headers=s["headers"]).json()
    # snapshot unchanged despite mutated DB
    assert got["results"][0]["statistic"] == pytest.approx(8.027, abs=0.001)


# ── 14. Pro-gating + ownership on new endpoints ──────────────────

def test_pro_gating_and_ownership(client):
    c, db_path = client
    free = _seed(db_path, tier="free")
    r = _wizard(c, free, {"goal": "relationship", "outcome": {"question_id": free["ids"]["s1"]}})
    assert r.status_code == 403
    pro = _seed(db_path)  # different user, pro
    other = create_jwt({"user_id": str(uuid.uuid4()), "email": "x@test.com"})
    r2 = c.post(f"/surveys/{pro['sid']}/wizard",
                json={"goal": "relationship", "outcome": {"question_id": pro["ids"]["s1"]},
                      "data_source": "actual"},
                headers={"Authorization": f"Bearer {other}"})
    assert r2.status_code == 404
    r3 = c.post(f"/surveys/{pro['sid']}/analyses",
                json={"analysis_type": "chi_square", "data_source": "actual",
                      "question_ids": [pro["ids"]["g"], pro["ids"]["f"]]},
                headers={"Authorization": f"Bearer {other}"})
    assert r3.status_code == 404


# ── 15. Zero credits across every inferential test ───────────────

def test_no_credit_after_all_inferential_tests(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    conn = _conn(db_path)
    before = conn.execute("SELECT kredit_remaining FROM users WHERE id=?", (s["uid"],)).fetchone()[0]
    conn.close()
    bodies = [
        {"analysis_type": "ttest_independent", "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["g"]},
        {"analysis_type": "ttest_paired", "outcome": {"construct_id": cid}, "outcome2": {"question_id": s["ids"]["m1"]}},
        {"analysis_type": "anova_oneway", "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["f"]},
        {"analysis_type": "mann_whitney", "outcome": {"question_id": s["ids"]["e1"]}, "grouping_question_id": s["ids"]["g"]},
        {"analysis_type": "kruskal_wallis", "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["f"]},
        {"analysis_type": "wilcoxon", "outcome": {"construct_id": cid}, "outcome2": {"question_id": s["ids"]["m1"]}},
        {"analysis_type": "correlation", "variables": [{"construct_id": cid}, {"question_id": s["ids"]["m1"]}]},
        {"analysis_type": "chi_square", "question_ids": [s["ids"]["g"], s["ids"]["f"]]},
    ]
    for b in bodies:
        assert _run(c, s, b).status_code == 200, b["analysis_type"]
    conn = _conn(db_path)
    after = conn.execute("SELECT kredit_remaining FROM users WHERE id=?", (s["uid"],)).fetchone()[0]
    conn.close()
    assert before == after


# ── 16-18. Edges: listwise/pairwise missing, construct vs item, pilot filter ─

def test_missing_values_listwise_per_test(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    # paired: r30 (m1 missing) dropped -> 29 pairs
    rp = _run(c, s, {"analysis_type": "ttest_paired",
                     "outcome": {"construct_id": cid}, "outcome2": {"question_id": s["ids"]["m1"]}})
    assert rp.json()["results"][0]["n_pairs"] == 29
    # group test on m1: Female group loses r30 -> n=14
    rg = _run(c, s, {"analysis_type": "ttest_independent",
                     "outcome": {"question_id": s["ids"]["m1"]}, "grouping_question_id": s["ids"]["g"]})
    groups = {g["group"]: g for g in rg.json()["results"][0]["groups"]}
    assert groups["Male"]["n"] == 15 and groups["Female"]["n"] == 14
    # correlation: pairwise deletion -> SAT-m1 n=29 while SAT-e1 n=30
    rc = _run(c, s, {"analysis_type": "correlation",
                     "variables": [{"construct_id": cid}, {"question_id": s["ids"]["m1"]},
                                   {"question_id": s["ids"]["e1"]}]})
    ns = {(p["variable_a"], p["variable_b"]): p["n"] for p in rc.json()["results"][0]["pairs"]}
    assert ns[("SAT", f"Q{s['ids']['m1']}")] == 29
    assert ns[("SAT", f"Q{s['ids']['e1']}")] == 30


def test_construct_composite_vs_single_item_outcome(client):
    c, db_path = client
    s = _seed(db_path)
    cid = _mk_sat(c, s)
    # construct composite outcome: t=8.027 (see test 1)
    r1 = _run(c, s, {"analysis_type": "ttest_independent",
                     "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["g"]})
    assert r1.json()["results"][0]["statistic"] == pytest.approx(8.027, abs=0.001)
    # single likert item m1 outcome — independent: t=4.4738 df=27 p=1.25e-04 d=1.6625
    r2 = _run(c, s, {"analysis_type": "ttest_independent",
                     "outcome": {"question_id": s["ids"]["m1"]}, "grouping_question_id": s["ids"]["g"]})
    res = r2.json()["results"][0]
    assert res["statistic"] == pytest.approx(4.474, abs=0.001)
    assert res["df"] == pytest.approx(27, abs=0.001)
    assert res["effect_size"]["value"] == pytest.approx(1.6625, abs=0.001)
    # non-likert outcome rejected
    r3 = _run(c, s, {"analysis_type": "ttest_independent",
                     "outcome": {"question_id": s["ids"]["f"]}, "grouping_question_id": s["ids"]["g"]})
    assert r3.status_code == 422


def test_data_source_pilot_filter(client):
    c, db_path = client
    s = _seed(db_path, with_pilot=True)
    cid = _mk_sat(c, s)
    r = c.post(f"/surveys/{s['sid']}/analyses",
               json={"analysis_type": "ttest_independent", "data_source": "pilot",
                     "outcome": {"construct_id": cid}, "grouping_question_id": s["ids"]["g"]},
               headers=s["headers"])
    assert r.status_code == 200
    res = r.json()["results"][0]
    # only the 4 pilot responses (2 Male / 2 Female) — actual's 30 rows excluded
    groups = {g["group"]: g for g in res["groups"]}
    assert groups["Male"]["n"] == 2 and groups["Female"]["n"] == 2
