"""Phase 10 T2：市场端点——频率契约形状 / insufficient 200 口径 / 参数校验 / 溯源。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn
from tests.test_stats import _jobs


@pytest.fixture()
def client(clean_db):
    """client + conn：conn 供 _jobs 数据工厂使用（同一 test 库连接）。"""
    app = create_app()

    def _override():
        yield clean_db

    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as c:
        yield c, clean_db


def test_market_skills_contract_shape(client):
    """35 岗 → 200 契约形状（§2.11）；service 超集字段必须被裁剪（D3）。"""
    c, conn = client
    _jobs(conn, 35)
    r = c.get("/api/market/skills")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"market", "window", "sample_size", "confidence",
                         "source_distribution", "skills"}
    assert body["market"] == "china"
    assert body["sample_size"] == 35
    assert body["confidence"] == "low"            # 30 <= 35 < 50
    assert body["window"]["start"] and body["window"]["end"]
    # demo_dataset = tier_a → 聚合为 tier 键（契约格式）
    assert body["source_distribution"] == {"tier_a": 1.0}

    rag = next(s for s in body["skills"] if s["skill_id"] == "RAG")
    assert rag["frequency"] == 1.0
    assert rag["jd_count"] == 35
    assert rag["evidence_ref"] == "/api/market/skills/RAG/evidence"
    # 超集字段剥离：service 的 canonical_name/stats_filter/method_version 不得出现
    assert "canonical_name" not in rag
    assert "stats_filter" not in body and "method_version" not in body


def test_market_skills_insufficient_200(client):
    """N=5 < 30 → 200 + insufficient:true（冻结口径：正确行为非故障，非错误体）。"""
    c, conn = client
    _jobs(conn, 5)
    r = c.get("/api/market/skills")
    assert r.status_code == 200
    body = r.json()
    assert body == {"market": "china", "sample_size": 5,
                    "insufficient": True, "skills": []}


def test_market_skills_invalid_params(client):
    """market/category/min_sample 非法 → 422 统一 VALIDATION_ERROR 体。"""
    c, _ = client
    assert c.get("/api/market/skills?market=us").status_code == 422
    assert c.get("/api/market/skills?category=nonexistent").status_code == 422
    assert c.get("/api/market/skills?min_sample=0").status_code == 422
    r = c.get("/api/market/skills?market=us")
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_market_skills_partial_window_rejected(client):
    """窗口只给一端 → 422（边界校验边界拒——service 会静默忽略，API 层必须明示）。"""
    c, _ = client
    r = c.get("/api/market/skills?window_start=2026-08-01")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "成对" in r.json()["error"]["message"]


def test_market_skills_city_slice(client):
    """city 切片生效：35 北京 + 5 杭州 → 杭州 insufficient / 北京 35。"""
    c, conn = client
    _jobs(conn, 35, city="北京")
    _jobs(conn, 5, tag="hz", city="杭州")
    r_hz = c.get("/api/market/skills?city=杭州")
    assert r_hz.status_code == 200
    assert r_hz.json()["sample_size"] == 5
    assert r_hz.json()["insufficient"] is True
    r_bj = c.get("/api/market/skills?city=北京")
    assert r_bj.json()["sample_size"] == 35
    assert "insufficient" not in r_bj.json()


def test_evidence_structure(client):
    """§2.12 溯源底账：逐条 JD 证据，collected_at ISO 字符串，契约键裁剪。"""
    c, conn = client
    _jobs(conn, 35)
    r = c.get("/api/market/skills/RAG/evidence")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"skill_id", "jd_refs"}
    assert body["skill_id"] == "RAG"
    assert len(body["jd_refs"]) == 35
    ref = body["jd_refs"][0]
    assert set(ref) == {"job_id", "title", "source_type",
                        "evidence_text", "source_url", "collected_at"}
    assert isinstance(ref["job_id"], int)
    assert "RAG" in ref["evidence_text"]
    assert isinstance(ref["collected_at"], str) and "T" in ref["collected_at"]


def test_evidence_unknown_skill_404(client):
    """词表外技能 → 404 统一 NOT_FOUND 体。"""
    c, conn = client
    _jobs(conn, 35)
    r = c.get("/api/market/skills/不存在的技能/evidence")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "不存在的技能" in body["error"]["message"]


def test_evidence_respects_stats_filter(client):
    """溯源底账同 STATS_FILTER 口径：user_submitted + market_analysis 属口径内；
    读侧口径恒定——底账行数与频率 jd_count 完全一致，不因端点不同而漂移。"""
    c, conn = client
    _jobs(conn, 35)
    _jobs(conn, 5, consent="market_analysis", source="user_contribution",
          source_type="user_submitted", tag="u")
    r = c.get("/api/market/skills/RAG/evidence")
    assert len(r.json()["jd_refs"]) == 40
    freq = c.get("/api/market/skills").json()
    rag_freq = next(s for s in freq["skills"] if s["skill_id"] == "RAG")
    assert rag_freq["jd_count"] == len(r.json()["jd_refs"])
