"""Phase 10 T3：画像端点——FakeLLM 三分支 / 契约裁剪 / GET / DELETE。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn
from skillgap.api.routes_profile import make_resume_extractor
from tests.profile_fixtures import (
    EXTRACTION_A, RESUME_A, FakeResumeExtractor,
)


@pytest.fixture()
def client(clean_db):
    """(client, conn)；extractor 默认 Fake 成功（单测试可覆写 _extractor）。"""
    app = create_app()

    def _override():
        yield clean_db

    def _fake_extractor():
        return FakeResumeExtractor(EXTRACTION_A)

    app.dependency_overrides[get_conn] = _override
    app.dependency_overrides[make_resume_extractor] = _fake_extractor
    with TestClient(app) as c:
        yield c, clean_db


def test_analyze_success_contract(client):
    """§2.5 成功：candidate 自动创建；契约裁剪——notices 不得出现。"""
    c, _ = client
    r = c.post("/api/resumes/analyze", json={"resume_text": RESUME_A})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"candidate_id", "skills", "soft_profile"}
    assert "notices" not in body                      # CLI 超集字段剥离
    assert isinstance(body["candidate_id"], int)

    rag = next(s for s in body["skills"] if s["skill_id"] == "RAG")
    assert rag["level"] == 4
    assert rag["evidences"][0]["type"] == "project_detail"
    assert "pgvector" in rag["evidences"][0]["text"]
    assert rag["evidences"][0]["evidence_ref"].startswith("resume#L")
    sp = body["soft_profile"]
    assert sp["experience_years"]["value"] == 2
    assert sp["languages"] is None


def test_analyze_length_validation(client):
    """长度越界 → 422 VALIDATION_ERROR（50 字下限）。"""
    c, _ = client
    r = c.post("/api/resumes/analyze", json={"resume_text": "太短"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "50" in body["error"]["message"]


def test_analyze_extraction_failed_502(client):
    """Fake 分支 2：抽取器重试后仍失败 → 502 LLM_EXTRACTION_FAILED，不降级。"""
    c, _ = client
    from skillgap.extract.llm_extractor import ExtractionFailed

    class Failing:
        def extract_full(self, resume_text):
            raise ExtractionFailed("简历抽取重试 2 次后仍失败: schema")

    c.app.dependency_overrides[make_resume_extractor] = lambda: Failing()
    r = c.post("/api/resumes/analyze", json={"resume_text": RESUME_A})
    assert r.status_code == 502
    body = r.json()
    assert body["error"]["code"] == "LLM_EXTRACTION_FAILED"
    assert body["error"]["details"]["retries"] == 2


def test_analyze_llm_error_502(client):
    """Fake 分支 3：上游网络/超时错误 → 502 LLM_TIMEOUT（details 携带原因类名）。"""
    c, _ = client
    from skillgap.llm.provider import LLMError

    class Dead:
        def extract_full(self, resume_text):
            raise LLMError("connection timeout after 60s")

    c.app.dependency_overrides[make_resume_extractor] = lambda: Dead()
    r = c.post("/api/resumes/analyze", json={"resume_text": RESUME_A})
    assert r.status_code == 502
    body = r.json()
    assert body["error"]["code"] == "LLM_TIMEOUT"
    assert body["error"]["details"]["cause"] == "LLMError"


def test_analyze_existing_candidate_reuse(client):
    """带 candidate_id 二次分析 → 同一 candidate（D1 替换式，技能不重复）。"""
    c, _ = client
    r1 = c.post("/api/resumes/analyze", json={"resume_text": RESUME_A})
    cid = r1.json()["candidate_id"]
    r2 = c.post("/api/resumes/analyze",
                json={"resume_text": RESUME_A, "candidate_id": cid})
    assert r2.json()["candidate_id"] == cid
    skills = c.get(f"/api/candidates/{cid}/profile").json()["skills"]
    rag_rows = [s for s in skills if s["skill_id"] == "RAG"]
    assert len(rag_rows) == 1                 # 替换式不残留旧行


def test_profile_get_evidence_chain(client):
    """§2.6 GET：每技能证据链完整；evidence_ref=null（D2 原文不落库）。"""
    c, _ = client
    cid = c.post("/api/resumes/analyze",
                 json={"resume_text": RESUME_A}).json()["candidate_id"]
    r = c.get(f"/api/candidates/{cid}/profile")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"candidate_id", "skills", "soft_profile"}
    rag = next(s for s in body["skills"] if s["skill_id"] == "RAG")
    for ev in rag["evidences"]:
        assert ev["evidence_ref"] is None     # 与 §2.5 会话内值不同
    assert rag["confidence"] > 0


def test_profile_not_found(client):
    """不存在 candidate → 404 统一体。"""
    c, _ = client
    r = c.get("/api/candidates/99999/profile")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_delete_candidate_cascade(client):
    """§2.7 DELETE → 204；级联后 profile 404；重复删 404。"""
    c, conn = client
    cid = c.post("/api/resumes/analyze",
                 json={"resume_text": RESUME_A}).json()["candidate_id"]
    assert c.delete(f"/api/candidates/{cid}").status_code == 204
    assert c.get(f"/api/candidates/{cid}/profile").status_code == 404
    assert c.delete(f"/api/candidates/{cid}").status_code == 404
    # 级联实证：candidate_skill 无残留
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM candidate_skill "
                    "WHERE candidate_id = %s", (cid,))
        assert cur.fetchone()["n"] == 0
