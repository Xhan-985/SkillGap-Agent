"""ROI 优先级纯函数（Phase 8，DATA_MODEL §4 冻结公式）。

potential_gain(s) = Demand(s) × Gap(s) ÷ Cost(s)

口径（docs/plans/2026-09-03-phase8-recommendation.md D1-D6）：
- cost_value：low=1 / mid=2 / high=3（§4.2 映射表）
- demand = 最新快照 frequency；频次 < MIN_FREQUENCY（0.20）不入清单
  （与 gap 类目聚合规则同源——DECISION_LOG D-2026-09-03-13）
- gap 复用 gap-v1 星级差（单一事实来源，本模块只消费）
- 排序：potential_gain 降序，同分按 frequency 降序，Top-K=10
- sample_size < 30 → SAMPLE_INSUFFICIENT 标记（不隐藏、不臆造）
- rationale 模板：数字 100% 来自 item 字段（D3）

规则计算（M9 红线：分数路径零模型调用）：零 skillgap 依赖，守卫测试锁定。
版本 roi-v1——公式/阈值/排序任一变更升 patch 并重跑 E3。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

ROI_VERSION = "roi-v1"
COST_VALUE = {"low": 1.0, "mid": 2.0, "high": 3.0}
MIN_FREQUENCY = 0.20          # 入清单阈值（与 gap 类目规则同源）
MIN_SAMPLE = 30               # 快照样本下限（低于则标记薄样本）
TOP_K = 10
_COST_LABEL = {"low": "低", "mid": "中", "high": "高"}


def potential_gain(frequency: float, gap: int, cost: str) -> float:
    """Demand × Gap ÷ Cost；零需求/零缺口 → 0（不除零）。"""
    if frequency <= 0 or gap <= 0:
        return 0.0
    return frequency * gap / COST_VALUE[cost]


def compute_priority(gap_items: Sequence[Mapping]) -> list[dict]:
    """gap-v1 聚合输出 + learning_cost → 排序后 Top-K 优先级清单。

    gap_items: [{skill, frequency, sample_size, evidence_ref, gap,
                 cost, type(genuine/transferable)}]
    """
    scored = []
    for it in gap_items:
        if it["frequency"] < MIN_FREQUENCY or it["gap"] <= 0:
            continue
        pg = potential_gain(float(it["frequency"]), int(it["gap"]),
                            it["cost"])
        scored.append({
            "skill": it["skill"],
            "frequency": float(it["frequency"]),
            "sample_size": int(it["sample_size"]),
            "evidence_ref": it.get("evidence_ref"),
            "gap": int(it["gap"]),
            "cost": it["cost"],
            "potential_gain": round(pg, 2),
            "type": it.get("type", "genuine"),
            "demand_status": ("OK" if int(it["sample_size"]) >= MIN_SAMPLE
                              else "SAMPLE_INSUFFICIENT"),
            "formula_version": ROI_VERSION,
        })
    scored.sort(key=lambda x: (-x["potential_gain"], -x["frequency"],
                               x["skill"]))
    return scored[:TOP_K]


def render_rationale(item: Mapping, time_budget_days: int) -> str:
    """确定性模板（D3）：四要素叙事，数字 100% 来自 item 字段。"""
    freq_pct = item["frequency"] * 100
    cost_lbl = _COST_LABEL[item["cost"]]
    parts = [
        f"{item['skill']}：市场需求频次 {freq_pct:.0f}%"
        f"（样本 {item['sample_size']}），当前缺口 {item['gap']} 星，"
        f"学习成本{cost_lbl}（{item['potential_gain']:.2f} = 频次×缺口÷成本），"
    ]
    if item.get("type") == "transferable":
        parts.append("已有相邻技能证据可迁移、补齐成本低；")
    parts.append(f"建议在 {time_budget_days} 天预算内优先投入。")
    if item.get("demand_status") == "SAMPLE_INSUFFICIENT":
        parts.append("（注意：快照样本薄，需求频次解释力有限）")
    return "".join(parts)
