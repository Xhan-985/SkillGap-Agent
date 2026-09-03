"""Skill Gap 纯函数（Phase 6，DATA_MODEL §4.2/§4.4）。

gap(s) = clamp(required_level − actual_level, ≥ 0)——纯星级差，
confidence 不进 gap（conf_factor 属 Phase 7 match 公式，2026-08-31
评审 H1 修复口径；DECISION_LOG C1 裁决）。

规则计算非 LLM（ROADMAP Phase 6 自检红线）：本模块零 skillgap 依赖，
守卫测试锁定。口径版本 gap-v1——变更须同步单测 + DECISION_LOG。
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

GAP_METHOD_VERSION = "gap-v1"

INTENSITY_LEVELS: dict[str, int] = {
    "精通": 5, "熟练": 4, "熟悉": 3, "了解": 2,
}
NICE_TO_HAVE_CAP = 2          # nice_to_have 封顶（DATA_MODEL §4.2）
NULL_INTENSITY_MUST = 3       # must_have 且 intensity 缺失 → 熟悉中性档
EVIDENCE_THRESHOLD = 0.5      # transferable 判定的证据线（§4.4）


def required_level(importance: str, intensity: str | None) -> int:
    """job_skill(importance, intensity) → 要求星级（§4.2 映射）。

    must_have：程度词映射，缺失取 3（熟悉中性档）；
    nice_to_have：一律封顶 2。词表外输入 → ValueError。
    """
    if importance not in ("must_have", "nice_to_have"):
        raise ValueError(f"importance 词表外取值: {importance!r}")
    if intensity is None:
        return (NULL_INTENSITY_MUST if importance == "must_have"
                else NICE_TO_HAVE_CAP)
    if intensity not in INTENSITY_LEVELS:
        raise ValueError(f"intensity 词表外取值: {intensity!r}")
    if importance == "nice_to_have":
        return min(INTENSITY_LEVELS[intensity], NICE_TO_HAVE_CAP)
    return INTENSITY_LEVELS[intensity]


def gap(required: int, actual: int) -> int:
    """clamp(required − actual, ≥ 0)。无记录技能由调用方传 actual=0。"""
    return max(0, required - actual)


def classify(skills_with_evidence: Mapping[str, float],
             related_map: Mapping[str, Iterable[str]],
             gap_skills: Iterable[str]) -> dict[str, str]:
    """缺口技能 → genuine / transferable（§4.4 冻结规则）。

    genuine     ⇔ 相关技能集（自身 + parent + transferable_to 关联，由
                  related_map 给出，须含自身）内无任何 confidence ≥ 0.5 证据
    transferable ⇔ 相关技能集内存在 confidence ≥ 0.5 证据
    """
    out: dict[str, str] = {}
    for s in gap_skills:
        related = set(related_map.get(s, (s)))
        related.add(s)
        has_evidence = any(
            skills_with_evidence.get(t, 0.0) >= EVIDENCE_THRESHOLD
            for t in related)
        out[s] = "transferable" if has_evidence else "genuine"
    return out
