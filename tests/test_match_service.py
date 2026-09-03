"""Phase 7 服务层 + 解释层单测（真实 PG；LLM 用 Fake gateway）。"""
import pytest

from skillgap.match.explanation import (
    check_consistency, generate_llm_explanation, render_template,
)
from skillgap.match.service import (
    CandidateNotFound, ExplanationInconsistency, JobNotFound, match_score,
)
from skillgap.profile.service import analyze_resume
from tests.profile_fixtures import EXTRACTION_A, FakeResumeExtractor
from tests.test_schema import _insert_job, _job_kwargs, _source


def _mk_job(clean_db, **kw):
    sid = _source(clean_db)
    kw.setdefault("content_hash", "h-match")
    return _insert_job(clean_db, **_job_kwargs(sid, **kw))


def _req(clean_db, job_id, skill, importance="must_have", intensity=None):
    sid = clean_db.execute(
        "SELECT id FROM skill WHERE canonical_name = %s", (skill,)
    ).fetchone()["id"]
    clean_db.execute(
        """INSERT INTO job_skill
           (job_id, skill_id, importance, intensity, evidence_text,
            extracted_by) VALUES (%s, %s, %s, %s, %s, 'manual')""",
        (job_id, sid, importance, intensity, f"要求 {skill}"))
    clean_db.commit()


def _mk_candidate(clean_db, extraction, resume):
    return analyze_resume(clean_db, resume,
                          FakeResumeExtractor(extraction))["candidate_id"]


class FakeLLM:
    """LLM gateway 桩：返回固定 content。"""

    def __init__(self, content):
        self.content = content
        self.calls = 0

    def chat(self, messages, response_json=False):
        self.calls += 1
        class R:
            pass
        r = R()
        r.content = self.content
        return r


# ---- 单岗匹配 + 落库 ----

def test_match_score_basic_and_persisted(clean_db):
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "RAG", "must_have", "熟练")
    _req(clean_db, jid, "Python", "must_have", "精通")
    out = match_score(clean_db, cid, jid)
    assert out["scoring_version"] == "1.0.0"
    assert set(out["breakdown"]) == {"coverage", "importance_coverage",
                                     "evidence_quality",
                                     "experience_relevance"}
    assert "Python" in out["weak_skills"]       # A: Python L3 < 精通5
    assert "RAG" in out["strong_skills"]        # A: RAG L4 ≥ 熟练4
    assert "explanation" in out
    # 落库回读一致
    row = clean_db.execute(
        """SELECT overall_score, breakdown, scoring_version
           FROM match_result WHERE candidate_id = %s AND job_id = %s""",
        (cid, jid)).fetchone()
    assert float(row["overall_score"]) == out["overall_score"]
    assert row["scoring_version"] == "1.0.0"
    assert row["breakdown"]["coverage"] == out["breakdown"]["coverage"]


def test_match_score_structured_groups(clean_db):
    """三组带结构（API §2.8：strong 带 confidence）。"""
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "Docker", "must_have", "熟悉")    # missing
    out = match_score(clean_db, cid, jid)
    assert out["missing_skills"] == ["Docker"]


def test_match_no_must_neutral_flag(clean_db):
    """e2-024 场景：无 must → importance_coverage=0.5 + neutral_flags。"""
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "MySQL", "nice_to_have", "了解")
    out = match_score(clean_db, cid, jid)
    assert out["breakdown"]["importance_coverage"] == 0.5
    assert "no_must_have" in out["neutral_flags"]


def test_match_invalid_when_no_skills(clean_db):
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)            # 无 job_skill 行
    out = match_score(clean_db, cid, jid)
    assert out["invalid"] == "no_skills"
    assert out["breakdown"]["coverage"] == 0.0


def test_match_not_found(clean_db):
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    with pytest.raises(JobNotFound):
        match_score(clean_db, cid, job_id=999)
    with pytest.raises(CandidateNotFound):
        match_score(clean_db, 999, job_id=jid)


def test_match_idempotent_persistence(clean_db):
    """重复评分 → 多行留痕（历史记录），不覆盖。"""
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "RAG", "must_have", "熟练")
    match_score(clean_db, cid, jid)
    match_score(clean_db, cid, jid)
    n = clean_db.execute(
        "SELECT count(*) AS n FROM match_result WHERE job_id = %s",
        (jid,)).fetchone()["n"]
    assert n == 2


# ---- 解释层 ----

def _fake_result():
    return {"overall_score": 72.5,
            "breakdown": {"coverage": 0.68, "importance_coverage": 0.60,
                          "evidence_quality": 0.81,
                          "experience_relevance": 0.5},
            "strong_skills": ["python", "rag"], "weak_skills": ["docker"],
            "missing_skills": ["mcp"], "neutral_flags": ["soft_not_evaluable"],
            "invalid": None}


def test_template_explanation_numbers_consistent():
    r = _fake_result()
    text = render_template(r)
    assert check_consistency(text, r) == []


def test_check_consistency_catches_alien_numbers():
    r = _fake_result()
    bad_text = "综合匹配 99 分，覆盖率 0.37。"
    bad = check_consistency(bad_text, r)
    assert "99" in bad and "0.37" in bad


def test_llm_explanation_via_fake_gateway(clean_db):
    """LLM 解释走 gateway；一致数字通过、不一致数字抛错。"""
    r = _fake_result()
    gw_ok = FakeLLM("综合匹配 72.5 分。覆盖率 68%，证据质量 0.81，"
                    "达标 2 项，缺失 1 项（mcp）。")
    text = generate_llm_explanation(gw_ok, r)
    assert check_consistency(text, r) == []
    assert gw_ok.calls == 1

    gw_bad = FakeLLM("综合 88 分，覆盖率 90%。")
    text_bad = generate_llm_explanation(gw_bad, r)
    assert check_consistency(text_bad, r) != []


def test_match_service_llm_explain_degrades_on_llm_failure(clean_db):
    """LLM 网络失败 → 降级模板（不抛错）。"""
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "RAG", "must_have", "熟练")

    class FailingGW:
        def chat(self, *a, **kw):
            raise RuntimeError("网络故障")

    out = match_score(clean_db, cid, jid, explain_llm=True,
                      gateway=FailingGW())
    assert "综合匹配" in out["explanation"]      # 模板降级特征
    assert check_consistency(out["explanation"], out) == []


def test_match_service_llm_explain_raises_on_inconsistent(clean_db):
    """LLM 返回自算数字 → ExplanationInconsistency（调用方决定降级）。"""
    cid = _mk_candidate(clean_db, EXTRACTION_A, "简历 A" * 30)
    jid = _mk_job(clean_db)
    _req(clean_db, jid, "RAG", "must_have", "熟练")
    gw = FakeLLM("综合 99.9 分，远超预期！")
    with pytest.raises(ExplanationInconsistency):
        match_score(clean_db, cid, jid, explain_llm=True, gateway=gw)
