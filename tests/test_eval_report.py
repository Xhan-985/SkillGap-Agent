"""评测报告生成测试（Phase 9 T3——结构/版本三元组/差异箭头/时间序列）。"""
from __future__ import annotations

import json

from skillgap.eval.report import generate_report

E1, E2, E3 = "skill_extraction", "matching", "recommendation"


def _insert_run(conn, eval_type, verdict, metrics, dataset="v1",
                prompt="p1", model="m", n=1):
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO eval_run (eval_type, dataset_version,
               prompt_version, model, metrics, sample_size, verdict)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)""",
            (eval_type, dataset, prompt, model,
             json.dumps(metrics), n, verdict))
    conn.commit()


def _seed_three_types(conn):
    """三类型各一条 pass run（最简全绿场景）。"""
    _insert_run(conn, E1, "pass",
                {"f1": 0.9, "precision": 0.9, "recall": 0.9,
                 "macro_f1": 0.8, "evidence_rate": 1.0,
                 "importance_accuracy": 0.9})
    _insert_run(conn, E2, "pass",
                {"spearman": 0.84, "mae": 9.4, "jaccard": 0.98,
                 "macro_f1": 0.98, "scoring_version": "1.0.0"})
    _insert_run(conn, E3, "pass",
                {"ndcg@5": 0.65, "precision@5": 0.6, "hit_rate@3": 1.0,
                 "coverage": 0.95})


# ---------- §0 结构 ----------

def test_report_structure_sections(clean_db):
    """四段结构（D3）：版本三元组 / 关键指标 / 时间序列 / 诚实边界。"""
    _seed_three_types(clean_db)
    md = generate_report(clean_db)
    assert md.startswith("# SkillGap 评测报告")
    assert "## 1. 版本三元组" in md
    assert "## 2. 关键指标" in md
    assert "## 3. eval_run 时间序列" in md
    assert "## 4. 诚实边界" in md


def test_empty_db_renders_without_crash(clean_db):
    """空库（首次跑分前）：不崩，明示无记录。"""
    md = generate_report(clean_db)
    assert "无评测记录" in md
    assert "## 4. 诚实边界" in md


def test_overall_header_from_gate(clean_db):
    """头部汇总门禁复用 gate：E1 warn + E2/E3 pass → overall=warn。"""
    _insert_run(clean_db, E1, "warn", {"f1": 0.86})
    _insert_run(clean_db, E2, "pass", {"spearman": 0.84})
    _insert_run(clean_db, E3, "pass", {"ndcg@5": 0.65})
    md = generate_report(clean_db)
    assert "汇总门禁：**warn**" in md


# ---------- §1 版本三元组 ----------

def test_version_triple_table(clean_db):
    """三元组呈现：E2 scoring 取自 metrics；E1/E3 无 → '—'；
    表按核心类型排序 E1→E2→E3（非字母序）。"""
    _seed_three_types(clean_db)
    md = generate_report(clean_db)
    # E2 行含 scoring_version=1.0.0；E1/E3 行为 —
    e2_line = [ln for ln in md.splitlines()
               if ln.startswith("| E2 ")][0]
    assert "1.0.0" in e2_line
    e1_line = [ln for ln in md.splitlines()
               if ln.startswith("| E1 ")][0]
    assert " — " in e1_line and "v1" in e1_line and "p1" in e1_line
    # §1 表顺序：E1 在 E2 前，E2 在 E3 前
    body = md.split("## 2.")[0]
    assert body.index("| E1 ") < body.index("| E2 ") < body.index("| E3 ")


# ---------- §2 关键指标 + 差异箭头 ----------

def test_diff_arrows_vs_previous_run(clean_db):
    """差异箭头：§2 每类型只呈现最新一条；下降 ↓ / 持平 → / 首条基线。"""
    _insert_run(clean_db, E1, "pass", {"f1": 0.90})
    _insert_run(clean_db, E1, "warn", {"f1": 0.85})   # 最新：↓ vs #1
    _insert_run(clean_db, E2, "pass", {"spearman": 0.84})  # 单条 → 基线
    md = generate_report(clean_db)
    sec = [ln for ln in md.splitlines() if ln.startswith("### E1")][0]
    assert "run #2 vs #1（同版本）" in sec
    assert "↓ -0.0500" in md
    assert "基线（首条）" in md


def test_diff_prefers_same_version_prev(clean_db):
    """同版本优先：紧邻上一条跨版本、更早一条同版本 → 取同版本那条。"""
    _insert_run(clean_db, E1, "pass", {"f1": 0.90}, dataset="v1")
    _insert_run(clean_db, E1, "pass", {"f1": 0.50}, dataset="v2")  # #2 同版本
    _insert_run(clean_db, E1, "pass", {"f1": 0.90}, dataset="v1")  # #3 紧邻
    _insert_run(clean_db, E1, "warn", {"f1": 0.45}, dataset="v2")  # #4 最新
    md = generate_report(clean_db)
    sec = [ln for ln in md.splitlines() if ln.startswith("### E1")][0]
    assert "run #4 vs #2（同版本）" in sec
    assert "↓ -0.0500" in md


def test_diff_cross_version_marked(clean_db):
    """无同版本基线时退回紧邻上一条，但明示跨版本（诚实优先）。"""
    _insert_run(clean_db, E1, "pass", {"f1": 0.90}, dataset="v1")
    _insert_run(clean_db, E1, "warn", {"f1": 0.85}, dataset="v2")  # 紧邻但跨版本
    md = generate_report(clean_db)
    sec = [ln for ln in md.splitlines() if ln.startswith("### E1")][0]
    assert "run #2 vs #1（跨版本，谨慎解读）" in sec


def test_diff_flat_when_identical(clean_db):
    _insert_run(clean_db, E1, "pass", {"f1": 0.85})
    _insert_run(clean_db, E1, "pass", {"f1": 0.85})   # 持平
    md = generate_report(clean_db)
    assert "→ 持平" in md


def test_prev_run_missing_metric_key(clean_db):
    """上一条 run 无该指标键 → 明示而非报错。"""
    _insert_run(clean_db, E2, "pass", {"spearman": 0.84})
    _insert_run(clean_db, E2, "pass",
                {"spearman": 0.84, "mae": 9.4, "jaccard": 0.98,
                 "macro_f1": 0.98})
    md = generate_report(clean_db)
    assert "—（上一条无此指标）" in md


def test_judge_reference_row_present_but_not_gating(clean_db):
    """judge 均分呈现为参考行并明示不进门禁。"""
    _insert_run(clean_db, E3, "pass",
                {"ndcg@5": 0.65, "judge": {"mean": 5.0, "n_judged": 5,
                                           "rubric_version": "rubric-v1"}})
    md = generate_report(clean_db)
    assert "judge 均分：5.0000" in md
    assert "永不进门禁" in md


def test_unknown_key_metrics_type_degrades(clean_db):
    """data_quality（E5）无关键指标定义：优雅降级列出 metrics 键。"""
    _insert_run(clean_db, "data_quality", "warn",
                {"null_rate": 0.01})
    md = generate_report(clean_db)
    assert "该类型未定义关键指标" in md
    assert "null_rate" in md
    assert "E5 数据质量" in md


# ---------- §3 时间序列 ----------

def test_timeseries_lists_all_history_with_headline(clean_db):
    """时间序列一行一条全量历史；头名指标 E1=f1 / E2=spearman / E3=ndcg@5。"""
    _seed_three_types(clean_db)
    _insert_run(clean_db, E1, "block", {"f1": 0.0})
    _insert_run(clean_db, E1, "pass", {"f1": 0.9})
    md = generate_report(clean_db)
    assert "| 1 |" in md and "| 2 |" in md and "| 3 |" in md
    assert "| 4 |" in md and "| 5 |" in md
    assert "f1=0.0000" in md
    assert "spearman=0.8400" in md
    assert "ndcg@5=0.6500" in md
    # 全绿→后插的 block 在历史里、但最新是 pass（§1 表以最新为准）
    e1_latest = [ln for ln in md.splitlines()
                 if ln.startswith("| E1 ")][0]
    assert "pass" in e1_latest


# ---------- 输出 ----------

def test_out_path_writes_file_and_returns_same_content(clean_db, tmp_path):
    """--out 写文件，返回值与文件内容一致。"""
    _seed_three_types(clean_db)
    out = tmp_path / "report.md"
    md = generate_report(clean_db, out_path=out)
    assert out.read_text(encoding="utf-8") == md
    assert "## 3. eval_run 时间序列" in md
