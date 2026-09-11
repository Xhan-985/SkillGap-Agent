"""Phase 10 T1：API 骨架——health / 统一错误体 / dependency_overrides 注入。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError


@pytest.fixture()
def client(clean_db):
    """TestClient + get_conn 覆写为 clean_db 连接（test 库，不触主库）。"""
    app = create_app()

    def _override():
        yield clean_db

    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as c:
        yield c


def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] is True
    assert body["llm"] in ("configured", "not_configured")  # 报告配置状态，不真实探活


def test_unknown_route_unified_404(client):
    r = client.get("/api/nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"] and "details" in body["error"]


def test_api_error_unified_body(client):
    """业务错误 ApiError → 统一错误体（在临时路由上验证 handler 行为）。"""
    app = create_app()

    @app.get("/api/_boom")
    def boom():
        raise ApiError(502, "LLM_EXTRACTION_FAILED", "抽取失败（测试）",
                       {"retries": 2})

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/_boom")
    assert r.status_code == 502
    body = r.json()
    assert body["error"]["code"] == "LLM_EXTRACTION_FAILED"
    assert body["error"]["message"] == "抽取失败（测试）"
    assert body["error"]["details"] == {"retries": 2}


def test_validation_error_unified_body(client):
    """Query/path 校验失败 → 422 + VALIDATION_ERROR 统一体（FastAPI 原生格式被替换）。"""
    app = create_app()

    from fastapi import Query

    @app.get("/api/_needint")
    def needint(n: int = Query()):
        return {"n": n}

    with TestClient(app) as c:
        r = c.get("/api/_needint")          # 缺必填参数
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"]["errors"]       # 携带原始校验详情（截断至 10 条）


def test_health_connection_closed_per_request(clean_db):
    """每请求连接纪律：deps.get_conn 生成器 yield 后关闭（原生依赖真实开合）。"""
    import psycopg
    conns = []

    def _track():
        conn = psycopg.connect(
            "postgresql://skillgap:skillgap@localhost:5432/skillgap_test",
            row_factory=psycopg.rows.dict_row)
        conns.append(conn)
        try:
            yield conn
        finally:
            conn.close()

    app = create_app()
    app.dependency_overrides[get_conn] = _track
    with TestClient(app) as c:
        assert c.get("/api/health").json()["db"] is True
    assert conns[0].closed, "请求结束后连接应已关闭"
