"""Phase 5 服务层单测（FakeResumeExtractor——零 LLM，真实 PG 测试库）。

画像 A/B/C 验收锚定 tests/profile_fixtures.py。
"""
import pytest

from skillgap.profile.service import (
    CandidateNotFound, ManualSkillError, ResumeValidationError,
    add_manual_skill, analyze_resume, delete_candidate, get_profile,
)
from tests.profile_fixtures import (
    EXTRACTION_A, EXTRACTION_B, EXTRACTION_C, EXTRACTION_C2,
    FakeResumeExtractor, RESUME_A, RESUME_B, RESUME_C, RESUME_C2,
)


def test_new_candidate_auto_created(clean_db):
    out = analyze_resume(clean_db, RESUME_A, FakeResumeExtractor(EXTRACTION_A))
    assert out["candidate_id"] == 1
    assert {s["skill_id"] for s in out["skills"]} == {"RAG", "Python"}


def test_candidate_not_found(clean_db):
    with pytest.raises(CandidateNotFound):
        analyze_resume(clean_db, RESUME_A, FakeResumeExtractor(EXTRACTION_A),
                       candidate_id=999)


def test_resume_length_validation(clean_db):
    with pytest.raises(ResumeValidationError):
        analyze_resume(clean_db, "太短", FakeResumeExtractor(EXTRACTION_A))
    with pytest.raises(ResumeValidationError):
        analyze_resume(clean_db, "长" * 20001, FakeResumeExtractor(EXTRACTION_A))


def test_profile_a_rich_details(clean_db):
    """画像 A：project_detail→conf 1.0；project_desc→0.6；soft_profile 落库。"""
    out = analyze_resume(clean_db, RESUME_A, FakeResumeExtractor(EXTRACTION_A))
    by_id = {s["skill_id"]: s for s in out["skills"]}
    assert by_id["RAG"]["confidence"] == 1.0
    assert by_id["RAG"]["level"] == 4
    assert by_id["RAG"]["evidences"][0]["type"] == "project_detail"
    assert by_id["Python"]["confidence"] == 0.6
    sp = out["soft_profile"]
    assert sp["experience_years"] == {"value": 2, "evidence_text": "两年后端开发经验"}
    assert sp["education"]["value"] == "本科·软件工程"
    assert sp["languages"] is None


def test_profile_b_bare_claims_low_confidence(clean_db):
    """画像 B（MVP 验收）：裸声明 conf=0.3 低分边界；soft_profile 全 null。"""
    out = analyze_resume(clean_db, RESUME_B, FakeResumeExtractor(EXTRACTION_B))
    by_id = {s["skill_id"]: s for s in out["skills"]}
    assert by_id["RAG"]["confidence"] == 0.3
    assert by_id["MCP"]["confidence"] == 0.3
    assert by_id["MCP"]["level"] == 2
    assert out["soft_profile"] == {"experience_years": None,
                                   "education": None, "languages": None}


def test_evidence_ref_line_number(clean_db):
    """D2：evidence_ref 返回证据所在行号（简历第 2/3 行）。"""
    out = analyze_resume(clean_db, RESUME_B, FakeResumeExtractor(EXTRACTION_B))
    by_id = {s["skill_id"]: s for s in out["skills"]}
    assert by_id["RAG"]["evidences"][0]["evidence_ref"] == "resume#L2"
    assert by_id["MCP"]["evidences"][0]["evidence_ref"] == "resume#L3"


def test_unresolved_skill_goes_to_candidates_with_notice(clean_db):
    from skillgap.models import (
        ResumeEvidence, ResumeExtraction, ResumeSkillAnnotation,
    )
    ext = ResumeExtraction(skills=[
        ResumeSkillAnnotation(raw_name="量子编程", level=3, evidences=[
            ResumeEvidence(type="bare_claim", text="熟悉 RAG"),
        ]),
    ])
    out = analyze_resume(clean_db, RESUME_B, FakeResumeExtractor(ext))
    assert out["skills"] == []
    assert out["notices"]["unresolved"] == ["量子编程"]
    row = clean_db.execute(
        "SELECT first_seen_job_id, status FROM new_skill_candidate "
        "WHERE raw_name = '量子编程'").fetchone()
    assert row["first_seen_job_id"] is None
    assert row["status"] == "pending"


def test_reanalyze_replaces_resume_skills(clean_db):
    """D1 替换式：旧 resume 技能行消失（证据级联），新结果入库。"""
    fake_a = FakeResumeExtractor(EXTRACTION_A)
    fake_b = FakeResumeExtractor(EXTRACTION_B)
    out1 = analyze_resume(clean_db, RESUME_A, fake_a)
    out2 = analyze_resume(clean_db, RESUME_B, fake_b, out1["candidate_id"])
    assert out2["candidate_id"] == out1["candidate_id"]
    profile = get_profile(clean_db, out1["candidate_id"])
    assert {s["skill_id"] for s in profile["skills"]} == {"RAG", "MCP"}
    n_evidence = clean_db.execute(
        "SELECT count(*) AS c FROM candidate_evidence").fetchone()["c"]
    assert n_evidence == 2   # A 的旧证据已级联清理


def test_manual_skill_preserved_on_reanalyze(clean_db):
    """画像 C（D1 全语义）：manual 行保留，同技能简历证据跳过 + notice。"""
    out = analyze_resume(clean_db, RESUME_C, FakeResumeExtractor(EXTRACTION_C))
    cid = out["candidate_id"]
    manual = add_manual_skill(clean_db, cid, "Python", 5)
    assert manual["confidence"] == 1.0

    out2 = analyze_resume(clean_db, RESUME_C2,
                          FakeResumeExtractor(EXTRACTION_C2), cid)
    assert out2["notices"]["manual_overridden"] == ["Python"]
    profile = get_profile(clean_db, cid)
    py = next(s for s in profile["skills"] if s["skill_id"] == "Python")
    assert py["source_type"] == "manual"
    assert py["level"] == 5            # manual 行不被简历覆盖
    assert py["confidence"] == 1.0
    assert py["evidences"][0]["type"] == "manual"
    assert py["evidences"][0]["text"] == "手动勾选"


def test_empty_extraction_creates_candidate(clean_db):
    """空抽取不报错、候选人照建（不伪造低置信技能——API §2.5 部分失败策略）。"""
    out = analyze_resume(clean_db, RESUME_C, FakeResumeExtractor(EXTRACTION_C))
    assert out["candidate_id"] == 1
    assert out["skills"] == []
    assert clean_db.execute(
        "SELECT count(*) AS c FROM candidate_skill").fetchone()["c"] == 0


def test_get_profile_structure(clean_db):
    analyze_resume(clean_db, RESUME_A, FakeResumeExtractor(EXTRACTION_A))
    profile = get_profile(clean_db, 1)
    assert profile["candidate_id"] == 1
    rag = next(s for s in profile["skills"] if s["skill_id"] == "RAG")
    assert rag["evidences"][0]["evidence_ref"] is None   # D2：不落库
    assert rag["evidences"][0]["weight"] == 1.0
    assert profile["soft_profile"]["experience_years"]["value"] == 2


def test_get_profile_not_found(clean_db):
    with pytest.raises(CandidateNotFound):
        get_profile(clean_db, 42)


def test_add_manual_skill_overrides_resume_row(clean_db):
    """D5：手动勾选整行替换 resume 来源行，confidence=1.0。"""
    out = analyze_resume(clean_db, RESUME_A, FakeResumeExtractor(EXTRACTION_A))
    add_manual_skill(clean_db, out["candidate_id"], "RAG", 5,
                     evidence_text="自评精通检索系统")
    profile = get_profile(clean_db, out["candidate_id"])
    rag = next(s for s in profile["skills"] if s["skill_id"] == "RAG")
    assert rag["source_type"] == "manual"
    assert rag["level"] == 5
    assert rag["confidence"] == 1.0
    assert rag["evidences"][0]["text"] == "自评精通检索系统"
    # 整行替换：只剩一条 manual 证据
    assert len(rag["evidences"]) == 1


def test_add_manual_skill_rejects_unknown_skill(clean_db):
    out = analyze_resume(clean_db, RESUME_C, FakeResumeExtractor(EXTRACTION_C))
    with pytest.raises(ManualSkillError, match="词表"):
        add_manual_skill(clean_db, out["candidate_id"], "量子编程", 3)


def test_add_manual_skill_rejects_bad_level(clean_db):
    out = analyze_resume(clean_db, RESUME_C, FakeResumeExtractor(EXTRACTION_C))
    with pytest.raises(ManualSkillError, match="level"):
        add_manual_skill(clean_db, out["candidate_id"], "Python", 6)


def test_delete_candidate_cascades(clean_db):
    out = analyze_resume(clean_db, RESUME_A, FakeResumeExtractor(EXTRACTION_A))
    assert delete_candidate(clean_db, out["candidate_id"]) is True
    assert clean_db.execute(
        "SELECT count(*) AS c FROM candidate_skill").fetchone()["c"] == 0
    assert clean_db.execute(
        "SELECT count(*) AS c FROM candidate_evidence").fetchone()["c"] == 0
    assert delete_candidate(clean_db, out["candidate_id"]) is False


def test_transaction_rollback_on_failure(clean_db):
    """中途异常不残留（CandidateNotFound 在插入后抛出 → rollback）。"""
    from skillgap.models import (
        ResumeEvidence, ResumeExtraction, ResumeSkillAnnotation,
    )
    ext = ResumeExtraction(skills=[
        ResumeSkillAnnotation(raw_name="RAG", level=4, evidences=[
            ResumeEvidence(type="project_detail",
                           text="pgvector+Hybrid Search+RRF+Rerank 搭建检索链路"),
        ]),
    ])
    # 不存在的 candidate_id：_ensure_candidate 在插入任何技能前抛出
    with pytest.raises(CandidateNotFound):
        analyze_resume(clean_db, RESUME_A, FakeResumeExtractor(ext),
                       candidate_id=777)
    assert clean_db.execute(
        "SELECT count(*) AS c FROM candidate").fetchone()["c"] == 0
