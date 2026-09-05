"""评测报告生成（Phase 9 T3 / D3——eval_run 历史 → Markdown 报告）。

定位：eval_run 是 source of truth，本模块只做**只读呈现**——
- 不重新判定指标（那是评测器职责）；verdict 直接读库
- 不重复阈值（gate 已汇总，报告复用 apply_gate 得 overall）
- 诚实边界（EVALUATION_PLAN §9）：小 N / 跨版本可比性 / judge 参考信号
  一律脚注明示，不粉饰
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from psycopg import Connection

from skillgap.eval.gate import CORE_TYPES, apply_gate, latest_runs

# 各评测类型的展示标签（报告可读性；eval_type 本名仍入库/入表）
TYPE_LABEL = {
    "skill_extraction": "E1 技能抽取",
    "matching": "E2 岗位匹配",
    "recommendation": "E3 学习推荐",
    "data_quality": "E5 数据质量",
}

# 关键指标（进入 §2 指标表的标量指标；嵌套 dict 如 per_case/adversarial
# 不进表——它们是过程数据，报告只呈现结论性指标）
KEY_METRICS: dict[str, list[str]] = {
    "skill_extraction": [
        "f1", "precision", "recall", "macro_f1",
        "evidence_rate", "importance_accuracy",
    ],
    "matching": ["spearman", "mae", "jaccard", "macro_f1"],
    "recommendation": ["ndcg@5", "precision@5", "hit_rate@3", "coverage"],
}

# 时间序列每类型展示的头名指标（一行一个结论）
HEADLINE = {
    "skill_extraction": "f1",
    "matching": "spearman",
    "recommendation": "ndcg@5",
    "data_quality": None,
}


def _fmt(v: Any) -> str:
    """指标格式化：float 统一 4 位小数；其余原样。"""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _fmt_ts(ts: Any) -> str:
    return str(ts)[:16] if ts is not None else ""


def _diff_cell(latest: dict, prev: dict | None, key: str) -> str:
    """差异单元格：与同类型上一条 run 的数值差（箭头只表示数值方向，
    不判读好坏——mae 之类逆向指标由读者按脚注语境解读）。"""
    if prev is None:
        return "基线（首条）"
    if key not in (prev.get("metrics") or {}):
        return "—（上一条无此指标）"
    delta = float(latest["metrics"][key]) - float(prev["metrics"][key])
    if abs(delta) < 1e-9:
        return "→ 持平"
    arrow = "↑" if delta > 0 else "↓"
    return f"{arrow} {delta:+.4f}"


def _fetch_all_runs(conn: Connection) -> list[dict]:
    """全部 eval_run 按 id 升序（时间序列用）。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, eval_type, dataset_version, prompt_version, model,
                      metrics, sample_size, verdict, created_at
               FROM eval_run ORDER BY id"""
        )
        return [dict(r) for r in cur.fetchall()]


def _pick_prev(hist: list[dict]) -> tuple[dict | None, str]:
    """选对比基线（诚实优先，§9）：优先同版本三元组（dataset+prompt）
    的上一条——同版本差异才是纯系统差异；无同版本时退回紧邻上一条
    并明示'跨版本'（口径变化，不能归因系统好坏）。
    """
    latest = hist[-1]
    for r in reversed(hist[:-1]):
        if (r["dataset_version"] == latest["dataset_version"]
                and r["prompt_version"] == latest["prompt_version"]):
            return r, f"vs #{r['id']}（同版本）"
    if len(hist) > 1:
        prev = hist[-2]
        return prev, f"vs #{prev['id']}（跨版本，谨慎解读）"
    return None, "首条基线"


def _label(eval_type: str) -> str:
    return TYPE_LABEL.get(eval_type, eval_type)


def generate_report(conn: Connection, out_path: Path | str | None = None) -> str:
    """生成 Markdown 评测报告（D3 结构：①版本三元组 ②关键指标+差异
    ③时间序列 ④诚实边界脚注）。out_path 给定则同时写文件；返回全文。
    """
    runs = _fetch_all_runs(conn)
    lines: list[str] = []

    # ---- 头部：标题 + 生成时间 + 汇总门禁（复用 gate，不重复判定） ----
    lines.append("# SkillGap 评测报告")
    lines.append("")
    lines.append(f"- 生成时间：{_fmt_ts(datetime.now())}（本地时区）")
    if runs:
        gate = apply_gate(latest_runs(conn))
        missing = (
            f"；缺基线 {gate['missing']}（warn 不阻断）" if gate["missing"] else ""
        )
        lines.append(
            f"- 汇总门禁：**{gate['overall']}**{missing}"
            "（judge 分数永不进门禁）"
        )
    else:
        lines.append("- 无评测记录（首次跑分前的正常态）")
    lines.append("")

    # ---- §1 版本三元组表（每类型最新 run） ----
    lines.append("## 1. 版本三元组（各类型最新 run）")
    lines.append("")
    if not runs:
        lines.append("> 无 eval_run 记录。")
    else:
        lines.append(
            "| 类型 | dataset | prompt | scoring | model | N | verdict |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        latest = latest_runs(conn)
        ordered = ([t for t in CORE_TYPES if t in latest]
                   + [t for t in latest if t not in CORE_TYPES])
        for et in ordered:
            run = latest[et]
            scoring = (run.get("metrics") or {}).get("scoring_version", "—")
            lines.append(
                f"| {_label(et)} | {run['dataset_version']} "
                f"| {run['prompt_version']} | {scoring} | {run['model']} "
                f"| {run['sample_size']} | {run['verdict']} |"
            )
    lines.append("")

    # ---- §2 关键指标表（最新 vs 同类型上一条） ----
    lines.append("## 2. 关键指标（最新 vs 上一条同类型 run）")
    lines.append("")
    by_type: dict[str, list[dict]] = {}
    for r in runs:
        by_type.setdefault(r["eval_type"], []).append(r)
    if not by_type:
        lines.append("> 无 eval_run 记录。")
    for et, hist in by_type.items():
        latest = hist[-1]
        prev, vs = _pick_prev(hist)
        lines.append(f"### {_label(et)}（run #{latest['id']} {vs}）")
        lines.append("")
        keys = KEY_METRICS.get(et, [])
        metrics = latest.get("metrics") or {}
        if keys:
            lines.append("| 指标 | 最新 | 与上一条差异 |")
            lines.append("|---|---|---|")
            for k in keys:
                if k not in metrics:
                    continue
                lines.append(
                    f"| {k} | {_fmt(metrics[k])} "
                    f"| {_diff_cell(latest, prev, k)} |"
                )
        else:
            lines.append(f"> 该类型未定义关键指标（metrics 键："
                         f"{', '.join(metrics) or '—'}）")
        # judge 参考行（存在才呈现；Warn 级信号，不进门禁）
        judge = metrics.get("judge")
        if isinstance(judge, dict) and "mean" in judge:
            lines.append("")
            lines.append(
                f"- judge 均分：{_fmt(judge['mean'])}"
                f"（rubric {judge.get('rubric_version', '?')}，"
                f"n={judge.get('n_judged', '?')}）——参考信号，永不进门禁"
            )
        lines.append("")

    # ---- §3 时间序列（全部历史，一行一条） ----
    lines.append("## 3. eval_run 时间序列（全部历史）")
    lines.append("")
    if not runs:
        lines.append("> 无 eval_run 记录。")
    else:
        lines.append(
            "| # | 类型 | dataset | prompt | model | N | verdict "
            "| 头名指标 | 时间 |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for r in runs:
            head = HEADLINE.get(r["eval_type"])
            head_cell = (
                f"{head}={_fmt((r.get('metrics') or {})[head])}"
                if head and head in (r.get("metrics") or {})
                else "—"
            )
            lines.append(
                f"| {r['id']} | {_label(r['eval_type'])} "
                f"| {r['dataset_version']} | {r['prompt_version']} "
                f"| {r['model']} | {r['sample_size']} | {r['verdict']} "
                f"| {head_cell} | {_fmt_ts(r['created_at'])} |"
            )
    lines.append("")

    # ---- §4 诚实边界（EVALUATION_PLAN §9） ----
    lines.append("## 4. 诚实边界")
    lines.append("")
    lines.append("- **跨版本对比**：差异仅在版本三元组（dataset/prompt/"
                 "scoring）一致时有意义；跨版本差异含口径变化，不能直接归因"
                 "于系统好坏（见 §1 表）。")
    lines.append("- **小 N**：各评测样本量见 §1 表（个位至几十量级），"
                 "单指标波动需谨慎解读，不粉饰不外推。")
    lines.append("- **judge 参考信号**：LLM-as-judge（rubric-v1）为 Warn 级"
                 "参考，分数永不进门禁（D-2026-09-04-16）。")
    lines.append("- **E1 非确定性**：LLM 指标存在方差（temperature=0 非"
                 "严格确定性承诺），同版本重跑允许 ≤3% 极差。")
    lines.append("")

    report = "\n".join(lines)
    if out_path is not None:
        Path(out_path).write_text(report, encoding="utf-8")
    return report
