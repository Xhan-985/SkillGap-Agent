"""证据置信度纯函数（Phase 5，DATA_MODEL §2.7）。

confidence = min(1.0, Σᵢ w₍ᵢ₎ × 0.5^(i-1))——证据权重降序排列后求和，
次数衰减 γ=0.5（第 2 条起贡献减半，防证据堆刷分）。

规则计算非 LLM（ROADMAP Phase 5 自检红线）：本模块零 skillgap 依赖，
守卫测试锁定。公式版本 conf-v1——变更须同步 docs/WEIGHT_RULES.md + 单测。
"""
from __future__ import annotations

from collections.abc import Sequence

EVIDENCE_WEIGHTS: dict[str, float] = {
    "project_detail": 1.0,   # 项目细节：具体技术栈 + 做法/量化结果
    "project_desc": 0.6,     # 项目提及：参与项目但缺细节
    "bare_claim": 0.3,       # 裸声明："熟悉 RAG" 无项目支撑
    "manual": 1.0,           # 手动勾选：用户显式确认
}
DECAY_FACTOR = 0.5
CONFIDENCE_METHOD_VERSION = "conf-v1"


def compute_confidence(weights: Sequence[float]) -> float:
    """Σ(权重) 归一化 + 次数衰减。空列表 → 0.0；结果 round 4 位。"""
    total = 0.0
    for i, w in enumerate(sorted(weights, reverse=True)):
        total += w * DECAY_FACTOR ** i
    return round(min(1.0, total), 4)
