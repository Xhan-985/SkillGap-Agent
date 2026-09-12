"""Phase 10 T4：match_score_text（jd_text 无状态模式，C4）。

锚定：与 job_id 模式无第二套公式——同 JD 双模式结果 dict 全等。
"""
from __future__ import annotations

import pytest

from skillgap.extract.analyzer import JDValidationError
from skillgap.match.service import (
    CandidateNotFound, match_score, match_score_text,
)
from skillgap.models import (
    JDExtraction, SkillAnnotation, SoftRequirement,
)
from skillgap.profile.service import analyze_resume
from tests.profile_fixtures import EXTRACTION_A, FakeResumeExtractor
from tests.test_match_service import _mk_job, _req
from tests.test_schema import _insert_job, _job_kwargs, _source

JD_TEXT = (
    "岗位：AI 应用开发工程师。\n"
    "职责：负责企业知识库系统的检索链路开发。\n"
    "要求：熟练掌握 RAG 检索链路搭建，精通 Python 后端开发。\n"
    "加分项：了解 Docker 容器化部署。\n"
    "经验要求：2年以上后端开发经验。\n"
)

SOFT_JSON = [{"type": "experience", "value": "2年以上",
              "evidence_text": "2年以上后端开发经验"}]


def _extraction() -> JDExtraction:
    return JDExtraction(
        skills=[
            SkillAnnotation(raw_name="RAG", importance="must_have",
                            intensity="熟练",
                            evidence_text="熟练掌握 RAG 检索链路搭建"),
            SkillAnnotation(raw_name="Python", importance="must_have",
                            intensity="精通",
                            evidence_text="精通 Python 后端开发"),
        ],
        soft_requirements=[
            SoftRequirement(type="experience", value="2年以上",
                            evidence_text="2年以上后端开发经验"),
        ],
    )


class FakeJDExtractor:
    """直返预设 JDExtraction（服务层测试替身，零 LLM）。"""

    def __init__(self, extraction: JDExtraction):
        self._extraction = extraction
        self.last_usage: dict = {}

    def extract_full(self, jd_text: str) -> JDExtraction:
        return self._extraction


def _mk_candidate(clean_db) -> int:
    return analyze_resume(clean_db, "简历 A" * 30,
                          FakeResumeExtractor(EXTRACTION_A))["candidate_id"]


def test_match_text_basic_and_no_persist(clean_db):
    """jd_text 模式出完整结果且不落库（无 consent 不入库——B1）。"""
    from psycopg.types.json import Json

    cid = _mk_candidate(clean_db)
    out = match_score_text(clean_db, cid, JD_TEXT, FakeJDExtractor(_extraction()))
    assert out["scoring_version"] == "1.0.0"
    assert set(out["breakdown"]) == {"coverage", "importance_coverage",
                                     "evidence_quality", "experience_relevance"}
    assert "RAG" in out["strong_skills"]          # 画像 A RAG L4 ≥ 熟练4
    assert "Python" in out["weak_skills"]         # Python L3 < 精通5
    assert out["breakdown"]["experience_relevance"] == 1.0  # 2年 ≥ 2年
    # 不落库：match_result 零行
    n = clean_db.execute("SELECT count(*) AS n FROM match_result")\
        .fetchone()["n"]
    assert n == 0


def test_dual_mode_consistency(clean_db):
    """C4 锚定：同 JD（同抽取输出入库 job_skill）双模式结果 dict 全等。"""
    from psycopg.types.json import Json

    cid = _mk_candidate(clean_db)
    sid = _source(clean_db)
    jid = _insert_job(clean_db, **_job_kwargs(
        sid, raw_text=JD_TEXT, content_hash="h-dual",
        soft_requirements=Json(SOFT_JSON)))
    _req(clean_db, jid, "RAG", "must_have", "熟练")
    _req(clean_db, jid, "Python", "must_have", "精通")

    text_out = match_score_text(clean_db, cid, JD_TEXT,
                                FakeJDExtractor(_extraction()))
    job_out = match_score(clean_db, cid, jid)
    assert text_out == job_out      # 无第二套公式：逐字段相等（含模板解释）


def test_match_text_length_validation(clean_db):
    """长度越界 → JDValidationError（analyzer 同口径 50-20000）。"""
    cid = _mk_candidate(clean_db)
    with pytest.raises(JDValidationError):
        match_score_text(clean_db, cid, "太短", FakeJDExtractor(_extraction()))


def test_match_text_unresolved_out_of_taxonomy(clean_db):
    """词表外 raw_name 不进 reqs（与管道 new_skill_candidate 同语义）。"""
    cid = _mk_candidate(clean_db)
    ext = JDExtraction(skills=[
        SkillAnnotation(raw_name="RAG", importance="must_have",
                        intensity="熟练", evidence_text="熟练掌握 RAG"),
        SkillAnnotation(raw_name="量子编程", importance="must_have",
                        intensity="精通", evidence_text="精通量子编程"),
    ])
    out = match_score_text(clean_db, cid, JD_TEXT,
                           FakeJDExtractor(ext), include_meta=True)
    assert "量子编程" not in out["missing_skills"]
    assert "RAG" in out["strong_skills"]
    assert out["_meta"]["unresolved"] == ["量子编程"]
    # 无词表外残留：三组技能全部来自词表
    req_names = {r["skill"] for r in out["_meta"]["reqs"]}
    assert req_names == {"RAG"}


def test_match_text_candidate_not_found(clean_db):
    with pytest.raises(CandidateNotFound):
        match_score_text(clean_db, 99999, JD_TEXT,
                         FakeJDExtractor(_extraction()))
