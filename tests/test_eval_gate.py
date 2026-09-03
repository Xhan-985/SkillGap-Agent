"""系统级评测门禁测试（Phase 9 T1——apply_gate 汇总/退出码/时点回放）。"""
from __future__ import annotations

import pytest

from skillgap.eval.gate import apply_gate, gate_exit_code, latest_runs

E1, E2, E3 = "skill_extraction", "matching", "recommendation"


def _run(verdict, **over):
    d = {"id": 1, "verdict": verdict, "dataset_version": "v",
         "model": "m", "sample_size": 1}
    d.update(over)
    return d


def _all(verdicts):
    return {E1: _run(verdicts[0]), E2: _run(verdicts[1]),
            E3: _run(verdicts[2])}


# ---------- apply_gate 纯函数 ----------

def test_all_pass():
    r = apply_gate(_all(["pass", "pass", "pass"]))
    assert r["overall"] == "pass"
    assert r["blocking"] is False
    assert r["missing"] == []


def test_single_block_blocks_overall():
    r = apply_gate(_all(["pass", "block", "pass"]))
    assert r["overall"] == "block"
    assert r["blocking"] is True


def test_warn_does_not_block():
    r = apply_gate(_all(["warn", "pass", "pass"]))
    assert r["overall"] == "warn"
    assert r["blocking"] is False


def test_missing_type_warns_not_blocks():
    """缺核心类型：warn 不 block（C3——首次跑分前的正常态）。"""
    r = apply_gate({E2: _run("pass"), E3: _run("pass")})
    assert r["overall"] == "warn"
    assert r["blocking"] is False
    assert r["missing"] == [E1]


def test_empty_runs_all_missing():
    r = apply_gate({})
    assert r["overall"] == "warn"
    assert r["missing"] == [E1, E2, E3]


def test_block_beats_missing():
    """缺类型 + 存在类型 block：block 优先（阻断是硬信号）。"""
    r = apply_gate({E2: _run("block")})
    assert r["overall"] == "block"


def test_judge_scores_never_gate():
    """judge 分数不进门禁（D-16 红线）：verdict=pass 的 run 即使
    metrics 里 judge mean=1.0 也不影响汇总——gate 只读 verdict 字段。"""
    r = apply_gate({E1: _run("pass"), E2: _run("pass"),
                    E3: _run("pass", metrics={"judge": {"mean": 1.0}})})
    assert r["overall"] == "pass"


def test_extra_type_factors_in():
    """核心三类型外的 eval_type（如 data_quality）若入库同样参与汇总。"""
    r = apply_gate({**_all(["pass", "pass", "pass"]),
                    "data_quality": _run("block")})
    assert r["overall"] == "block"


def test_exit_code_mapping():
    assert gate_exit_code({"blocking": True}) == 1
    assert gate_exit_code({"blocking": False}) == 0


# ---------- latest_runs（取数规则：每类型最新 / 时点回放） ----------

def _insert_run(conn, eval_type, verdict, dataset="v1"):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO eval_run (eval_type, dataset_version,
               prompt_version, model, metrics, sample_size, verdict)
               VALUES (%s, %s, 'p1', 'm', '{}'::jsonb, 1, %s)""",
            (eval_type, dataset, verdict))
    conn.commit()


def test_latest_runs_takes_newest_per_type(clean_db):
    _insert_run(clean_db, E1, "block")
    _insert_run(clean_db, E1, "pass")            # 新 → 覆盖旧的
    _insert_run(clean_db, E2, "warn")
    runs = latest_runs(clean_db)
    assert runs[E1]["verdict"] == "pass"
    assert runs[E2]["verdict"] == "warn"
    assert E3 not in runs
    assert apply_gate(runs)["missing"] == [E3]


def test_latest_runs_point_in_time(clean_db):
    """--run-id 时点回放：id ≤ N 的最新一条（演练"历史某时刻会不会被拦"）。"""
    _insert_run(clean_db, E1, "block")            # id=1
    _insert_run(clean_db, E1, "pass")            # id=2（修复后）
    runs_t1 = latest_runs(clean_db, run_id=1)
    assert apply_gate(runs_t1)["overall"] == "block"
    runs_now = latest_runs(clean_db)
    assert apply_gate(runs_now)["overall"] == "warn"   # E1 pass 但缺 E2/E3


def test_latest_runs_run_id_before_history_raises(clean_db):
    with pytest.raises(ValueError, match="不存在"):
        latest_runs(clean_db, run_id=1)
