"""贡献端点（API.md §2.2 POST jd/contribute + tasks 异步查询 + §2.14 DELETE）。

C2/D4：DB 任务表（migration 005）+ FastAPI BackgroundTasks——单进程
uvicorn 够用；任务内自建连接（不复用请求连接，请求关闭后后台仍需连接）。
D5：deletion_code 一次性展示——task.result 存明文，GET tasks/{id} 首次
返回后置 null（"已展示，请使用已保存的 code"）；DB 本体（deletion_code
表）仍只存哈希（§2.14 防探测纪律不变）。

失败语义（D4 不静默的具体化）：QuarantinedContribution / 管道异常 →
status=failed + error 明示；LLM 抽取失败 → 任务仍 completed +
extraction_status=pending（job 已入库，deletion_code 必须送达用户——
删除权合规优先；CLI backfill-extraction 可补抽）。
"""
from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, Field

from skillgap import db
from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError
from skillgap.config import settings
from skillgap.ingest.contribute import (
    ConsentRequired, QuarantinedContribution, contribute_jd, delete_contribution,
)

router = APIRouter(tags=["contribute"])


class ContributeRequest(BaseModel):
    """§2.2 Request；title 可选（空标题走质检 quarantine 明示——与 CLI
    --title 必填同口径，不静默拦截）。"""

    jd_text: str = Field(min_length=1, max_length=20000)
    consent: bool
    title: str = ""
    source_hint: str = "other"


def _new_conn():
    """D4：任务内自建连接（后台执行时请求连接已关闭）。"""
    return db.connect()


def _make_llm_extractor(conn):
    """LLM 装配（异步任务版）：key 缺失返回 None——任务降级为 completed +
    extraction_status=pending 明示（job 已入库不回滚），不静默。"""
    if not settings.llm_api_key:
        return None
    from skillgap.extract.llm_extractor import LLMSkillExtractor
    from skillgap.extract.prompt import PROMPT_VERSION
    from skillgap.llm.gateway import LLMGateway
    from skillgap.llm.provider import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url, api_key=settings.llm_api_key,
        model=settings.llm_model, timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries)
    return LLMSkillExtractor(LLMGateway(conn, provider, PROMPT_VERSION))


def _finish(conn, task_id: uuid.UUID, status: str, *,
            result: dict | None = None, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE task SET status = %s, result = %s::jsonb,
               error = %s, updated_at = now() WHERE id = %s""",
            (status, json.dumps(result, ensure_ascii=False) if result else None,
             error, task_id))
    conn.commit()


def run_contribute_task(task_id: uuid.UUID, jd_text: str, title: str,
                        source_hint: str, conn_factory, extractor_factory) -> None:
    """BackgroundTasks 任务体（C2/D4）：contribute_jd 管道 + LLM 抽取回填。"""
    conn = conn_factory()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE task SET status = 'running', updated_at = now() WHERE id = %s",
                (task_id,))
        conn.commit()
        try:
            outcome = contribute_jd(conn, jd_text=jd_text, consent=True,
                                    title=title, source_hint=source_hint)
        except QuarantinedContribution as e:
            conn.rollback()          # 事务可能 aborted；隔离暂存已各自 commit
            _finish(conn, task_id, "failed", error=str(e))
            return
        except ConsentRequired as e:  # 防御：路由层已同步拒绝，正常不可达
            conn.rollback()
            _finish(conn, task_id, "failed", error=str(e))
            return
        except Exception as e:
            conn.rollback()
            _finish(conn, task_id, "failed", error=f"{type(e).__name__}: {e}")
            return

        extraction_status: str | None = None
        if not outcome.deduplicated:
            extractor = extractor_factory(conn)
            if extractor is None:
                extraction_status = "pending"   # LLM 未配置：明示待回填
            else:
                from skillgap.extract.analyzer import backfill_job
                from skillgap.extract.llm_extractor import ExtractionFailed
                from skillgap.llm.provider import LLMError

                raw_text = conn.execute(
                    "SELECT raw_text FROM job WHERE id = %s",
                    (outcome.job_id,)).fetchone()["raw_text"]
                try:
                    backfill_job(conn, extractor, outcome.job_id, raw_text)
                    extraction_status = "done"
                except (ExtractionFailed, LLMError):
                    conn.rollback()
                    extraction_status = "pending"  # job 在库；deletion_code 照常送达

        payload = {
            "status": "completed",
            "job_id": outcome.job_id,
            "deduplicated": outcome.deduplicated,
            "pii_redaction": outcome.pii_redaction,
            "deletion_code": outcome.deletion_code,
        }
        if not outcome.deduplicated:
            payload["extraction_status"] = extraction_status
        _finish(conn, task_id, "completed", result=payload)
    finally:
        conn.close()


@router.post("/api/jd/contribute", status_code=202)
def contribute(body: ContributeRequest, background_tasks: BackgroundTasks,
               conn=Depends(get_conn)):
    """§2.2 匿名贡献 JD（opt-in）：consent=false 同步拒绝（不建任务）。"""
    if not body.consent:
        raise ApiError(422, "VALIDATION_ERROR",
                       "consent=false：未经同意不入库（B1 口径）")
    task_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute("INSERT INTO task (id, kind) VALUES (%s, 'jd_contribute')",
                    (task_id,))
    conn.commit()
    background_tasks.add_task(
        run_contribute_task, task_id, body.jd_text, body.title,
        body.source_hint, _new_conn, _make_llm_extractor)
    return {"task_id": str(task_id), "message": "脱敏与去重处理中"}


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str, conn=Depends(get_conn)):
    """任务状态查询；D5：deletion_code 一次性展示（首查返回后即置 null）。"""
    try:
        tid = uuid.UUID(task_id)
    except ValueError:
        raise ApiError(404, "NOT_FOUND", "task 不存在")
    row = conn.execute(
        "SELECT status, result, error FROM task WHERE id = %s", (tid,)
    ).fetchone()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "task 不存在")
    if row["status"] == "completed":
        result = dict(row["result"] or {})
        if result.get("deletion_code"):
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE task SET result = result || %s::jsonb,
                       updated_at = now() WHERE id = %s""",
                    (json.dumps({"deletion_code": None}), tid))
            conn.commit()
        return {"status": "completed", **result}
    if row["status"] == "failed":
        return {"status": "failed", "error": row["error"]}
    return {"status": row["status"]}


@router.delete("/api/contributions/{deletion_code}", status_code=204)
def delete(deletion_code: str, conn=Depends(get_conn)):
    """§2.14 凭 code 删除贡献（级联 job_skill/deletion_code）；库中
    只存哈希，明文 code 不落库。"""
    if not delete_contribution(conn, deletion_code):
        raise ApiError(404, "NOT_FOUND", "deletion_code 无效或贡献已删除")
    return Response(status_code=204)
