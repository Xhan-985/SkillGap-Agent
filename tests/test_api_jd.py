"""Phase 10 T5：JD 分析端点——无状态 / 失败明示 / soft 透传 / 库无新行。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn
from skillgap.api.routes_jd import make_jd_extractor
from skillgap.models import JDExtraction, SkillAnnotation, SoftRequirement
from tests.test_match_text import JD_TEXT


class FakeJDAnalyzer:
    """直返预设抽取（成功路径）；失败路径用 raise 子类。"""

    def __init__(self, extraction=None, error=None):
        self._extraction = extraction
        self._error = error
        self.last_usage = {"model": "fake", "total_tokens": 0}
        self.gateway = type("G", (), {"prompt_version": "p-fake"})()

    def extract_full(self, jd_text: str) -> JDExtraction:
        if self._error:
            raise self._error
        return self._extraction


def _extraction() -> JDExtraction:
    return JDExtraction(
        skills=[
            SkillAnnotation(raw_name="RAG", importance="must_have",
                            intensity="熟练",
                            evidence_text="熟练掌握 RAG 检索链路搭建"),
        ],
        soft_requirements=[
            SoftRequirement(type="experience", value="2年以上",
                            evidence_text="2年以上后端开发经验"),
        ],
    )


@pytest.fixture()
def client(clean_db):
    """(client, conn)；extractor 默认 Fake 成功。"""
    app = create_app()

    def _conn():
        yield clean_db

    app.dependency_overrides[get_conn] = _conn
    app.dependency_overrides[make_jd_extractor] = \
        lambda: FakeJDAnalyzer(_extraction())
    with TestClient(app) as c:
        yield c, clean_db


def test_jd_analyze_success_stateless(client):
    """§2.1 成功：结构断言 + soft_requirements 透传 + 库无新行（B1）。"""
    c, conn = client
    n_before = conn.execute(
        "SELECT count(*) AS n FROM job").fetchone()["n"]
    raw_before = conn.execute(
        "SELECT count(*) AS n FROM raw_jobs").fetchone()["n"]
    r = c.post("/api/jd/analyze", json={"jd_text": JD_TEXT,
                                        "title": "AI 应用工程师"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"job", "core_skills", "secondary_skills",
                         "soft_requirements", "extraction_meta"}
    assert body["job"]["market"] == "china"          # 中文 → china
    assert body["job"]["job_category"] in (
        "ai_application_dev", "agent_dev", "llm_infra", "data_ai")
    core = body["core_skills"][0]
    assert core["raw_name"] == "RAG"
    assert core["evidence_text"] in JD_TEXT          # 证据可溯
    assert body["soft_requirements"][0]["type"] == "experience"
    assert body["extraction_meta"]["model"] == "fake"
    # 无状态：job / raw_jobs 零新行
    assert conn.execute(
        "SELECT count(*) AS n FROM job").fetchone()["n"] == n_before
    assert conn.execute(
        "SELECT count(*) AS n FROM raw_jobs").fetchone()["n"] == raw_before


def test_jd_analyze_length_validation(client):
    """长度越界 → 422 VALIDATION_ERROR（50-20000 口径）。"""
    c, _ = client
    r = c.post("/api/jd/analyze", json={"jd_text": "太短"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "50" in r.json()["error"]["message"]


def test_jd_analyze_extraction_failed_502(client):
    """抽取失败 → 502 LLM_EXTRACTION_FAILED 明示（不降级）。"""
    c, _ = client
    from skillgap.extract.llm_extractor import ExtractionFailed

    c.app.dependency_overrides[make_jd_extractor] = lambda: FakeJDAnalyzer(
        error=ExtractionFailed("抽取重试 2 次后仍失败: schema"))
    r = c.post("/api/jd/analyze", json={"jd_text": JD_TEXT})
    assert r.status_code == 502
    body = r.json()
    assert body["error"]["code"] == "LLM_EXTRACTION_FAILED"
    assert body["error"]["details"]["retries"] == 2


def test_jd_analyze_llm_error_502(client):
    """上游网络错误 → 502 LLM_TIMEOUT（cause 保真）。"""
    c, _ = client
    from skillgap.llm.provider import LLMError

    c.app.dependency_overrides[make_jd_extractor] = lambda: FakeJDAnalyzer(
        error=LLMError("connection timeout"))
    r = c.post("/api/jd/analyze", json={"jd_text": JD_TEXT})
    assert r.status_code == 502
    body = r.json()
    assert body["error"]["code"] == "LLM_TIMEOUT"
    assert body["error"]["details"]["cause"] == "LLMError"
