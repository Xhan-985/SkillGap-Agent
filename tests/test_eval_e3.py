"""E3 评测器单测（指标纯函数 + runner 留痕；零真实 LLM 调用）。

口径（EVALUATION_PLAN §4 预声明）：
- nDCG@5：系统 Top5 × 标注相关性（2=高价值必补 / 1=值得补 / 0=低价值）
- Top-5 Precision@5：系统 Top5 中标注 ≥1 的比例
- Hit Rate@3：标注=2 的技能至少一个进 Top3
- verdict：nDCG ≥0.5 pass / ≥0.35 warn / block（起步线，E3-2026-09-03 复议）
"""
import math

import pytest

from skillgap.eval.e3 import (
    dcg, ndcg_at_k, precision_at_k, hit_rate_at_k, relevance_of,
)

REL = {"Python": 2, "MCP": 2, "Docker": 1, "Go": 0}


# ---- 指标纯函数 ----

def test_relevance_of_levels():
    assert relevance_of("必补、市场高频", "skill") == 2
    assert relevance_of("值得补", "skill") == 1
    assert relevance_of("低价值", "skill") == 0


def test_dcg_ideal_ordering():
    # 理想排序 [2,2,1,0] DCG 一定 >= 任何其他排列
    assert dcg([2, 2, 1, 0]) >= dcg([1, 2, 0, 2])


def test_dcg_gain_formula():
    # 增益 2^rel−1：dcg([2]) = (2^2−1)/log2(2) = 3
    assert dcg([2]) == pytest.approx(3.0)
    assert dcg([1, 1]) == pytest.approx(1 + 1 / math.log2(3))


def test_ndcg_perfect_is_1():
    assert ndcg_at_k([2, 2, 1, 0], [2, 2, 1, 0]) == 1.0


def test_ndcg_reversed_is_low():
    # 2^rel−1 增益下完全反序 ≈0.63：仍显著低于 1 但相对线性增益更宽容
    v = ndcg_at_k([0, 1, 2, 2], [2, 2, 1, 0])
    assert 0.0 < v < 0.7


def test_ndcg_k_truncates():
    """只看前 k=2 项；后面对调不影响。"""
    assert ndcg_at_k([2, 2, 0, 0], [2, 2, 1, 0], k=2) == 1.0
    assert ndcg_at_k([2, 2, 1, 0], [2, 2, 0, 1], k=2) == 1.0


def test_ndcg_empty_safe():
    assert ndcg_at_k([], []) == 0.0


def test_precision_at_k():
    # 系统 Top5=[A,B,C,D,E]，标注 {A:2, C:1, E:2} → P@5 = 3/5
    assert precision_at_k(["A", "B", "C", "D", "E"],
                          {"A": 2, "C": 1, "E": 2}) == 0.6


def test_hit_rate_at_k():
    # "MCP"（rel=2）在 Top3 → hit；必补技能全排 Top3 外 → miss
    assert hit_rate_at_k(["Python", "MCP", "Docker"], REL) == 1.0
    assert hit_rate_at_k(["Go", "Docker", "Kubernetes"], REL) == 0.0
