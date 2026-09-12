"""Phase 10 T4：匹配 + 缺口端点——契约对象数组 / 双模式 / explain 降级 / gaps。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn
from skillgap.api.routes_match import get_extractor_factory, get_gateway_factory
from skillgap.match.explanation import render_template
from skillgap.models import JDExtraction, SkillAnnotation
from skillgap.profile.service import analyze_resume
from tests.profile_fixtures import EXTRACTION_A, FakeResumeExtractor
from tests.test_match_text import (
    JD_TEXT, FakeJDExtractor, _extraction,
)
from tests.test_match_service import _mk_job, _req
from tests.test_stats import _jobs


class FakeGateway:
    """解释 gateway 桩：返回固定 content（含不一致数字用于拦截测试）。"""

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


@pytest.fixture()
def client(clean_db):
    """(client, conn)；extractor/gateway 工厂默认 Fake（单测试可覆写）。"""
    app = create_app()

    def _conn():
        yield clean_db

    app.dependency_overrides[get_conn] = _conn
    app.dependency_overrides[get_extractor_factory] = \
        lambda: (lambda: FakeJDExtractor(_extraction()))
    app.dependency_overrides[get_gateway_factory] = \
        lambda: (lambda: FakeGateway("综合得分 12345 分，非常好"))
    with TestClient(app) as c:
        yield c, clean_db


def _mk_candidate(conn) -> int:
    return analyze_resume(conn, "简历 A" * 30,
                          FakeResumeExtractor(EXTRACTION_A))["candidate_id"]


def _mk_job_with_reqs(conn) -> int:
    jid = _mk_job(conn)
    _req(conn, jid, "RAG", "must_have", "熟练")
    _req(conn, jid, "Python", "must_have", "精通")
    _req(conn, jid, "Docker", "must_have", "熟练")
    return jid


def test_match_job_id_mode_contract(client):
    """job_id 模式：三组对象数组 + weak 成因区分 + missing JD 行号溯源。"""
    c, conn = client
    cid = _mk_candidate(conn)
    jid = _mk_job_with_reqs(conn)
    r = c.post("/api/match", json={"candidate_id": cid, "job_id": jid})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"overall_score", "scoring_version", "breakdown",
                         "strong_skills", "weak_skills", "missing_skills",
                         "explanation"}
    # 超集键剥离（D3）
    assert "neutral_flags" not in body and "invalid" not in body

    strong = body["strong_skills"]
    assert next(s for s in strong if s["skill_id"] == "RAG")["evidence_ref"] \
        is None                        # 画像行号不落库（D2）
    py = next(w for w in body["weak_skills"] if w["skill_id"] == "Python")
    assert py["note"] == "等级未达标" and py["confidence"] > 0
    dk = next(m for m in body["missing_skills"] if m["skill_id"] == "Docker")
    assert dk["required_importance"] == "must_have"
    assert dk["jd_evidence_ref"].startswith("jd#L")
    assert body["explanation"]           # 默认模板非空


def test_match_jd_text_mode(client):
    """jd_text 模式：Fake 注入抽取器，200 且不落库。"""
    c, conn = client
    cid = _mk_candidate(conn)
    r = c.post("/api/match", json={"candidate_id": cid, "jd_text": JD_TEXT})
    assert r.status_code == 200
    body = r.json()
    assert body["overall_score"] > 0
    ids = {s["skill_id"] for s in body["strong_skills"]}
    assert "RAG" in ids
    n = conn.execute("SELECT count(*) AS n FROM match_result")\
        .fetchone()["n"]
    assert n == 0


def test_match_mode_mutual_exclusion(client):
    """jd_text 与 job_id 必须二选一：都给/都不给 → 422。"""
    c, conn = client
    cid = _mk_candidate(conn)
    r1 = c.post("/api/match", json={"candidate_id": cid})
    r2 = c.post("/api/match", json={"candidate_id": cid, "jd_text": JD_TEXT,
                                    "job_id": 1})
    assert r1.status_code == 422 and r2.status_code == 422
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"


def test_match_candidate_not_found(client):
    """candidate 不存在 → 404（jd_text 模式，Fake 抽取器在场）。"""
    c, _ = client
    r = c.post("/api/match", json={"candidate_id": 99999, "jd_text": JD_TEXT})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_match_explain_inconsistency_fallback(client):
    """explain=true：LLM 叙事数字不一致（12345 不在 breakdown 集）→ 拦截
    降级确定性模板（对齐 Phase 8 agent verify 先例）。"""
    c, conn = client
    cid = _mk_candidate(conn)
    jid = _mk_job_with_reqs(conn)
    r = c.post("/api/match", json={"candidate_id": cid, "job_id": jid,
                                   "explain": True})
    assert r.status_code == 200
    explanation = r.json()["explanation"]
    assert "12345" not in explanation
    # 与确定性模板完全一致（数字仅由 breakdown 携带）
    from skillgap.match.service import match_score
    ref = match_score(conn, cid, jid)
    assert explanation == ref["explanation"]


def test_gaps_job_mode(client):
    """gaps 单岗模式：结构断言（required/actual/gap/demand/cost）。"""
    c, conn = client
    cid = _mk_candidate(conn)
    jid = _mk_job_with_reqs(conn)
    r = c.get(f"/api/candidates/{cid}/gaps?job_id={jid}")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "job" and body["job_id"] == jid
    assert body["gap_version"] == "gap-v1"
    py = next(g for g in body["gaps"] if g["skill_id"] == "Python")
    assert py["required_level"] == 5 and py["actual_level"] == 3
    assert py["gap"] == 2
    assert "frequency" in py["demand"] and py["cost"] in ("low", "mid", "high")
    dk = next(g for g in body["gaps"] if g["skill_id"] == "Docker")
    assert dk["gap"] == 4


def test_gaps_category_mode(client):
    """gaps 类目聚合模式：频次 ≥0.20 入清单 + category_sample_size。"""
    c, conn = client
    _jobs(conn, 35)                      # RAG must 熟悉 + Python must 精通
    cid = _mk_candidate(conn)
    r = c.get(f"/api/candidates/{cid}/gaps"
              "?category=ai_application_dev&market=china")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "category"
    assert body["category_sample_size"] == 35
    py = next(g for g in body["gaps"] if g["skill_id"] == "Python")
    assert py["gap"] == 2 and py["demand"]["frequency"] == 1.0
    # RAG L4 ≥ required 3 → 无缺口，不出现
    assert all(g["skill_id"] != "RAG" for g in body["gaps"])


def test_gaps_mode_mutual_exclusion(client):
    """job_id 与 category 必须二选一：都给/都不给 → 422。"""
    c, conn = client
    cid = _mk_candidate(conn)
    r1 = c.get(f"/api/candidates/{cid}/gaps")
    r2 = c.get(f"/api/candidates/{cid}/gaps?job_id=1&category=ai_application_dev")
    assert r1.status_code == 422 and r2.status_code == 422
