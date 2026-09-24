"""Phase 11 T3：贡献删除端点（§2.14）——204 删除闭环 / 404 防探测。
Phase 11 T4：POST jd/contribute（§2.2，202 + BackgroundTasks）+ tasks
异步查询（D5 deletion_code 一次性展示语义）——FakeLLM 管道全链路。"""
from __future__ import annotations

import os
import re
import uuid as uuid_mod

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from skillgap.api import routes_contribute
from skillgap.api.app import create_app
from skillgap.api.deps import get_conn
from skillgap.config import settings
from skillgap.models import SkillAnnotation

TEST_URL = os.environ.get("TEST_DATABASE_URL", settings.test_database_url)

# 合法 JD fixture（≥50 字符 / 中文 / 无 spam / 单行不触发 template_like）
JD_TEXT = ("负责大模型应用开发，熟练使用 Python 与 RAG 技术栈，"
           "构建检索增强生成系统，优化向量数据库查询性能，"
           "与团队协作交付 AI 产品功能。")
JD_TITLE = "AI 应用工程师"

DEFAULT_ANNS = [{"raw_name": "Python", "importance": "must_have",
                 "intensity": "熟练", "evidence_text": "熟练使用 Python"}]


class _FakeExtractor:
    def __init__(self, anns, exc=None):
        self._anns = anns
        self._exc = exc
        self.calls = 0

    def extract(self, jd_text):
        self.calls += 1
        if self._exc:
            raise self._exc
        return [SkillAnnotation(**a) for a in self._anns]


def _install_fake_llm(monkeypatch, anns=None, exc=None) -> _FakeExtractor:
    fx = _FakeExtractor(anns if anns is not None else DEFAULT_ANNS, exc)
    monkeypatch.setattr(routes_contribute, "_make_llm_extractor",
                        lambda conn: fx)
    return fx


@pytest.fixture()
def client(clean_db, monkeypatch):
    """(client, conn)：请求连接 override；任务连接工厂 → 独立 test 库
    连接（D4 自建连接语义——任务 close 不影响请求连接）。"""
    app = create_app()

    def _override():
        yield clean_db

    def _task_conn():
        return psycopg.connect(TEST_URL, row_factory=dict_row)

    monkeypatch.setattr(routes_contribute, "_new_conn", _task_conn)
    app.dependency_overrides[get_conn] = _override
    with TestClient(app) as c:
        yield c, clean_db


def _contribute(c, jd_text=JD_TEXT, title=JD_TITLE, consent=True,
                source_hint="other"):
    return c.post("/api/jd/contribute", json={
        "jd_text": jd_text, "consent": consent, "title": title,
        "source_hint": source_hint})


# ---------- T4：POST jd/contribute + GET tasks/{id} ----------

def test_contribute_202_and_completed_shape(client, monkeypatch):
    """202 结构（task_id + message）→ 任务完成后契约形状全字段。"""
    _install_fake_llm(monkeypatch)
    c, _ = client
    r = _contribute(c)
    assert r.status_code == 202
    body = r.json()
    assert set(body) == {"task_id", "message"}
    assert body["message"] == "脱敏与去重处理中"
    task = c.get(f"/api/tasks/{body['task_id']}").json()
    assert task["status"] == "completed"
    assert isinstance(task["job_id"], int)
    assert task["deduplicated"] is False
    assert task["pii_redaction"]["rules_version"]
    assert re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", task["deletion_code"])
    assert task["extraction_status"] == "done"


def test_contribute_pipeline_job_and_skills_inserted(client, monkeypatch):
    """FakeLLM 管道：job 入库（来源/consent/source_hint）+ job_skill LLM 行
    + deletion_code 表存哈希（明文不落库）。"""
    _install_fake_llm(monkeypatch)
    c, conn = client
    task = c.get(f"/api/tasks/{_contribute(c, source_hint='boss').json()['task_id']}").json()
    job = conn.execute("SELECT * FROM job WHERE id = %s",
                       (task["job_id"],)).fetchone()
    assert job["source_type"] == "user_submitted"
    assert job["consent_status"] == "market_analysis"
    assert job["parsed_metadata"]["source_hint"] == "boss"
    assert job["parsed_metadata"].get("extraction_status") is None  # 回填已清
    js = conn.execute(
        "SELECT extracted_by FROM job_skill WHERE job_id = %s",
        (task["job_id"],)).fetchall()
    assert [r["extracted_by"] for r in js] == ["llm"]
    dc = conn.execute("SELECT code_hash FROM deletion_code").fetchone()
    assert dc["code_hash"] != task["deletion_code"]  # 库中只存哈希


def test_contribute_consent_false_rejected(client, monkeypatch):
    """consent=false 同步 422 拒绝（B1）——不建任务不入库。"""
    c, conn = client
    r = _contribute(c, consent=False)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert conn.execute("SELECT count(*) AS n FROM task").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == 0


def test_contribute_empty_jd_text_422(client):
    """空 jd_text → pydantic 校验 422（统一 VALIDATION_ERROR 错误体）。"""
    c, _ = client
    r = _contribute(c, jd_text="")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_contribute_deduplicated_passthrough(client, monkeypatch):
    """复跑幂等：同 JD 二次贡献 → deduplicated=true + 既有 job_id +
    deletion_code=null + 零 LLM 调用（去重命中即返回）。"""
    fx = _install_fake_llm(monkeypatch)
    c, _ = client
    t1 = c.get(f"/api/tasks/{_contribute(c).json()['task_id']}").json()
    t2 = c.get(f"/api/tasks/{_contribute(c).json()['task_id']}").json()
    assert t2["deduplicated"] is True
    assert t2["job_id"] == t1["job_id"]
    assert t2["deletion_code"] is None
    assert fx.calls == 1


def test_contribute_quarantine_failed(client, monkeypatch):
    """质检隔离：短文本 → task failed + error 明示（含 quarantine 与原因）；
    job 不入库，raw 留隔离复核队列。"""
    _install_fake_llm(monkeypatch)
    c, conn = client
    task = c.get(f"/api/tasks/{_contribute(c, jd_text='太短').json()['task_id']}").json()
    assert task["status"] == "failed"
    assert "quarantine" in task["error"]
    assert conn.execute("SELECT count(*) AS n FROM job").fetchone()["n"] == 0
    assert conn.execute(
        "SELECT count(*) AS n FROM raw_jobs WHERE status = 'quarantined'"
    ).fetchone()["n"] == 1


def test_task_failure_error_not_silent(client, monkeypatch):
    """管道意外异常 → status=failed + error 携异常类型与信息（D4 不静默）。"""
    def _boom(*a, **kw):
        raise RuntimeError("db exploded")
    monkeypatch.setattr(routes_contribute, "contribute_jd", _boom)
    c, _ = client
    task = c.get(f"/api/tasks/{_contribute(c).json()['task_id']}").json()
    assert task["status"] == "failed"
    assert "RuntimeError" in task["error"]
    assert "db exploded" in task["error"]


def test_deletion_code_one_time_semantics(client, monkeypatch):
    """D5 核心：deletion_code 首查返回 → 二查为 null（已展示）；
    DB result 同步置 null，deletion_code 表哈希保留（删除能力不丢）。"""
    _install_fake_llm(monkeypatch)
    c, conn = client
    task_id = _contribute(c).json()["task_id"]
    code = c.get(f"/api/tasks/{task_id}").json()["deletion_code"]
    assert re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", code)
    second = c.get(f"/api/tasks/{task_id}").json()
    assert second["deletion_code"] is None
    assert conn.execute(
        "SELECT result->>'deletion_code' AS dc FROM task WHERE id = %s",
        (task_id,)).fetchone()["dc"] is None
    assert conn.execute(
        "SELECT count(*) AS n FROM deletion_code").fetchone()["n"] == 1


def test_task_not_found(client):
    """未知 task_id → 404 统一 NOT_FOUND。"""
    c, _ = client
    r = c.get(f"/api/tasks/{uuid_mod.uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_task_invalid_uuid_not_found(client):
    """非法 uuid（探测）→ 404 同一错误体（不区分格式/存在性）。"""
    c, _ = client
    r = c.get("/api/tasks/not-a-uuid")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_contribute_llm_failure_still_completed_pending(client, monkeypatch):
    """LLM 抽取失败 → 任务仍 completed + extraction_status=pending 明示
    （job 已入库；deletion_code 照常送达——删除权合规优先）。"""
    from skillgap.llm.provider import LLMError
    _install_fake_llm(monkeypatch, exc=LLMError("upstream down"))
    c, conn = client
    task = c.get(f"/api/tasks/{_contribute(c).json()['task_id']}").json()
    assert task["status"] == "completed"
    assert task["extraction_status"] == "pending"
    assert task["deletion_code"] is not None
    assert conn.execute(
        "SELECT count(*) AS n FROM job_skill").fetchone()["n"] == 0


def test_contribute_no_llm_key_pending(client, monkeypatch):
    """LLM 未配置（工厂返回 None）→ completed + pending 明示（不静默）。"""
    monkeypatch.setattr(routes_contribute, "_make_llm_extractor",
                        lambda conn: None)
    c, _ = client
    task = c.get(f"/api/tasks/{_contribute(c).json()['task_id']}").json()
    assert task["status"] == "completed"
    assert task["extraction_status"] == "pending"


def test_contribute_pii_redaction_passthrough(client, monkeypatch):
    """JD 含手机号 → 脱敏后入库（raw_text 无原号）+ pii_redaction
    透传（rules_version + hits.phone）+ **落库元数据回写真实报告**
    （T8 走查缺陷 #2 回归锚：process_record 对已脱敏文本二次扫描恒空
    hits，贡献通道须覆盖——否则质量报表 PII 处置低报）。"""
    _install_fake_llm(monkeypatch)
    c, conn = client
    jd_with_phone = "联系我 13800138000。" + JD_TEXT
    task = c.get(f"/api/tasks/{_contribute(c, jd_text=jd_with_phone).json()['task_id']}").json()
    assert task["status"] == "completed"
    assert task["pii_redaction"]["hits"]["phone"] == 1
    row = conn.execute("SELECT raw_text, parsed_metadata FROM job WHERE id = %s",
                       (task["job_id"],)).fetchone()
    assert "13800138000" not in row["raw_text"]
    assert row["parsed_metadata"]["pii_redaction"]["hits"]["phone"] == 1
    assert row["parsed_metadata"]["pii_redaction"]["rules_version"] == "v1"


def test_task_pending_running_states(client):
    """瞬态：pending / running 返回 {status}（无 result 展开）。"""
    c, conn = client
    t_pending, t_running = uuid_mod.uuid4(), uuid_mod.uuid4()
    conn.execute(
        "INSERT INTO task (id, kind, status) VALUES (%s, 'jd_contribute', 'pending')",
        (t_pending,))
    conn.execute(
        "INSERT INTO task (id, kind, status) VALUES (%s, 'jd_contribute', 'running')",
        (t_running,))
    conn.commit()
    assert c.get(f"/api/tasks/{t_pending}").json() == {"status": "pending"}
    assert c.get(f"/api/tasks/{t_running}").json() == {"status": "running"}


# ---------- T3：§2.14 DELETE contributions ----------

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
