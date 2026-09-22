"""Phase 11 T3：贡献删除端点（§2.14）——204 删除闭环 / 404 防探测。
T4 将在本文件增补 POST jd/contribute + tasks 异步查询测试。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skillgap.api.app import create_app
from skillgap.api.deps import get_conn


@pytest.fixture()
def client(clean_db):
    """client + conn：conn 供数据工厂使用（同一 test 库连接）。"""
    app = create_app()

    def _override():
        yield clean_db

    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as c:
        yield c, clean_db


def _contribution(conn, code="AB12-CD34") -> int:
    """最小贡献 fixture：job + deletion_code（库中只存哈希）。"""
    from tests.test_schema import _insert_job, _job_kwargs, _source
    from skillgap.ingest.contribute import _hash_code

    sid = _source(conn)
    jid = _insert_job(conn, **_job_kwargs(
        sid, content_hash=f"h-{code}", source_type="user_submitted",
        source_url=None, consent_status="market_analysis"))
    conn.execute(
        "INSERT INTO deletion_code (job_id, code_hash) VALUES (%s, %s)",
        (jid, _hash_code(code)))
    conn.commit()
    return jid


def test_delete_contribution_204(client):
    """有效 code → 204 空 body + job 真删（级联 job_skill/deletion_code）。"""
    c, conn = client
    jid = _contribution(conn, "AB12-CD34")
    r = c.delete("/api/contributions/AB12-CD34")
    assert r.status_code == 204
    assert r.content == b""
    assert conn.execute(
        "SELECT count(*) AS n FROM job WHERE id = %s", (jid,)
    ).fetchone()["n"] == 0
    assert conn.execute(
        "SELECT count(*) AS n FROM deletion_code"
    ).fetchone()["n"] == 0                    # ON DELETE CASCADE


def test_delete_contribution_not_found(client):
    """错误 code → 404 统一 NOT_FOUND 错误体（API.md §0 形状）。"""
    c, _ = client
    r = c.delete("/api/contributions/ZZZZ-9999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_delete_contribution_anti_probe(client):
    """防探测（§2.14 纪律）：'已删除'与'从未存在'的 404 响应完全一致
    ——不向探测者区分 code 曾否有效。"""
    c, conn = client
    _contribution(conn, "AB12-CD34")
    assert c.delete("/api/contributions/AB12-CD34").status_code == 204
    again = c.delete("/api/contributions/AB12-CD34")   # 已删除
    never = c.delete("/api/contributions/WX00-YZ99")   # 从未存在
    assert again.status_code == never.status_code == 404
    assert again.json() == never.json()
