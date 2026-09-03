"""系统级评测门禁（Phase 9 D1/D2——EVALUATION_PLAN §8 的汇总出口）。

定位：把三评测器（E1/E2/E3）各自的 eval_run verdict 汇总成一道门禁。
- **不重新判定单指标**——那是评测器的职责（阈值表已在各模块冻结，
  verdict 落库即权威）；gate 只做"多类型汇总 + 退出码映射"
- judge 分数**永不进门禁**（rubric-v1 是 Warn 级参考信号，D-2026-09-04-16）
- 缺核心类型 → warn 不 block（首次跑分前的正常态，stderr 提示）
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from psycopg import Connection

# 三层评测的核心类型（E1/E2/E3）；eval_run CHECK 里的 data_quality
# （E5）不产生门禁——质量报告是观测信号不是回归门禁
CORE_TYPES = ("skill_extraction", "matching", "recommendation")

_RANK = {"pass": 0, "warn": 1, "block": 2}


def apply_gate(runs: Mapping[str, Mapping[str, Any]]) -> dict:
    """纯函数：{eval_type: run(至少含 verdict)} → 汇总判定。

    runs 取值来自 eval_run 行（dict）。规则：
    - 任一类型 verdict=block → overall=block（blocking=True，CI 阻断）
    - 无 block 但有 warn，或核心类型缺失 → overall=warn（不阻断）
    - 三类型齐全且全 pass → overall=pass
    """
    order = list(CORE_TYPES) + [k for k in runs if k not in CORE_TYPES]
    per_type: dict[str, dict] = {}
    overall = "pass"
    for et in order:
        run = runs.get(et)
        if run is None:
            per_type[et] = {"present": False, "verdict": None}
            continue
        v = run.get("verdict")
        per_type[et] = {
            "present": True, "verdict": v,
            "run_id": run.get("id"),
            "dataset_version": run.get("dataset_version"),
            "model": run.get("model"),
            "sample_size": run.get("sample_size"),
        }
        if v == "block":
            overall = "block"
        elif v == "warn" and _RANK[overall] < _RANK["warn"]:
            overall = "warn"

    missing = [et for et in CORE_TYPES
               if not per_type.get(et, {}).get("present")]
    if missing and overall == "pass":
        overall = "warn"
    return {"overall": overall, "per_type": per_type,
            "blocking": overall == "block", "missing": missing}


def latest_runs(conn: Connection, run_id: int | None = None) -> dict:
    """取每个 eval_type 的最新 eval_run（或 id ≤ run_id 的最新——时点门禁，
    供"回放历史某时刻会不会被拦"的演练/报告场景）。

    返回 {eval_type: row(dict)}；metrics 为 JSONB（psycopg 已解成 dict）。
    """
    sql = """SELECT DISTINCT ON (eval_type) id, eval_type, dataset_version,
                    prompt_version, model, metrics, sample_size, verdict,
                    created_at
             FROM eval_run"""
    params: tuple = ()
    if run_id is not None:
        sql += " WHERE id <= %s"
        params = (run_id,)
    sql += " ORDER BY eval_type, id DESC"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    if run_id is not None and not rows:
        raise ValueError(f"eval_run#{run_id} 及更早的历史不存在")
    return {r["eval_type"]: dict(r) for r in rows}


def gate_exit_code(result: Mapping[str, Any]) -> int:
    """退出码映射（C3）：block → 1（阻断合并）；warn/pass → 0。"""
    return 1 if result["blocking"] else 0
