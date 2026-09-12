"""Phase 10 T5：推荐端点——ROI 结构 / 预算过滤 / 守门 422 / 溯源。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn
from tests.test_recommend_service_fixtures import (
    seed_market, write_templates,
)


@pytest.fixture()
def client(clean_db):
    """(client, conn)；模板路径经环境无关注入——service 默认读 data/，
    测试用 tmp_path 文件（conftest 无 env 钩子，直接 monkeypatch 默认路径）。"""
    app = create_app()

    def _override():
        yield clean_db

    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as c:
        yield c, clean_db


@pytest.fixture()
def templates(tmp_path, monkeypatch):
    tp = write_templates(tmp_path)
    from skillgap.recommend import service as rec_service
    monkeypatch.setattr(rec_service, "DEFAULT_TEMPLATES_PATH", tp)
    return tp


def test_recommendations_contract(client, templates):
    """§2.10 成功：priority_items 结构 + rationale 模板渲染 + 版本。"""
    c, conn = client
    cid = seed_market(conn)
    r = c.post("/api/recommendations",
               json={"candidate_id": cid, "time_budget_days": 14})
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"candidate_id", "market", "time_budget_days",
                         "formula_version", "priority_items",
                         "project_suggestions"}
    assert body["formula_version"] == "roi-v1"
    item = body["priority_items"][0]
    assert set(item) >= {"skill", "frequency", "sample_size", "gap", "cost",
                         "potential_gain", "rationale"}
    assert item["potential_gain"] > 0
    assert item["rationale"]                 # 模板已渲染（非空）
    # 落库（service 语义，端点透传后仍成立）
    n = conn.execute(
        "SELECT count(*) AS n FROM recommendation WHERE candidate_id=%s",
        (cid,)).fetchone()["n"]
    assert n >= 1


def test_recommendations_budget_filter(client, templates):
    """budget=7 → est_days>7 的项目模板被过滤。"""
    c, conn = client
    cid = seed_market(conn)
    r = c.post("/api/recommendations",
               json={"candidate_id": cid, "time_budget_days": 7})
    sugg = r.json()["project_suggestions"]
    assert all(s["est_days"] <= 7 for s in sugg)


def test_recommendations_invalid_budget(client):
    """time_budget_days 词表外 → 422 VALIDATION_ERROR（统一体）。"""
    c, conn = client
    cid = seed_market(conn)
    r = c.post("/api/recommendations",
               json={"candidate_id": cid, "time_budget_days": 10})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_recommendations_insufficient_market_422(client, templates):
    """ADR-008 守门：global 无数据 → 422 SAMPLE_INSUFFICIENT 错误体
    （D2 双口径之决策侧——与 market/skills 200 灰态对照）。"""
    c, conn = client
    cid = seed_market(conn)            # 只种 china
    r = c.post("/api/recommendations",
               json={"candidate_id": cid, "market": "global"})
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "SAMPLE_INSUFFICIENT"
    assert "仅 0 岗" in body["error"]["message"]
    assert "ADR-008" in body["error"]["message"]


def test_recommendations_candidate_not_found(client, templates):
    c, _ = client
    r = c.post("/api/recommendations",
               json={"candidate_id": 99999})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_recommendations_invalid_market(client):
    c, _ = client
    r = c.post("/api/recommendations",
               json={"candidate_id": 1, "market": "us"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
