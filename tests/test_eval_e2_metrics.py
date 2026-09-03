"""E2 指标纯函数单测（EVALUATION_PLAN §3.2 阈值预声明；手写实现无 scipy）。

已知值用例锚定公式正确性；verdict 判定锚定阈值表。
"""
import pytest

from skillgap.eval.e2 import (
    E2_THRESHOLDS, compute_metrics, jaccard, mae, prf, spearman,
)


# ---- spearman（含并列秩平均） ----

def test_spearman_perfect_monotonic():
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)


def test_spearman_inverse():
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_spearman_known_value():
    """手算锚定：x=[1,2,2,4], y=[1,3,2,4] → 平均秩 rx=[1,2.5,2.5,4],
    ry=[1,3,2,4] → Pearson=4.5/√(4.5×5)=0.9487（含并列秩）。"""
    assert spearman([1, 2, 2, 4], [1, 3, 2, 4]) == pytest.approx(
        0.9486832980505138, abs=1e-6)


def test_spearman_with_ties_both_sides():
    """两侧并列手算：rx=[1.5,1.5,3], ry=[1,2.5,2.5] →
    ρ=0.75/1.5=0.5。"""
    assert spearman([1, 1, 2], [1, 2, 2]) == pytest.approx(0.5)


def test_spearman_constant_returns_zero():
    assert spearman([5, 5, 5], [1, 2, 3]) == 0.0


def test_spearman_empty():
    assert spearman([], []) == 0.0


# ---- mae / jaccard ----

def test_mae():
    assert mae([100, 50], [80, 60]) == pytest.approx(15.0)


def test_jaccard():
    assert jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
    assert jaccard(set(), set()) == 1.0        # 双空 = 完全一致


# ---- prf ----

def test_prf_micro_pooled():
    sys_groups = {"strong": {"python"}, "weak": {"docker"},
                  "missing": {"git"}}
    hum_groups = {"strong": {"python"}, "weak": set(),
                  "missing": {"docker", "git"}}
    p, r, f1 = prf(sys_groups, hum_groups)
    # 池化决策：TP=2（python, git），系统 3 个，人工 3 个
    assert p == pytest.approx(2 / 3)
    assert r == pytest.approx(2 / 3)
    assert f1 == pytest.approx(2 / 3)


def test_prf_missing_only():
    """Missing 组单独主报（缺口判定是核心输出）。"""
    sys_groups = {"strong": set(), "weak": set(), "missing": {"a", "b"}}
    hum_groups = {"strong": set(), "weak": set(), "missing": {"b", "c"}}
    p, r, f1 = prf(sys_groups, hum_groups, group="missing")
    assert p == pytest.approx(0.5)
    assert r == pytest.approx(0.5)
    assert f1 == pytest.approx(0.5)


def test_prf_macro():
    sys_groups = {"strong": {"python"}, "weak": set(), "missing": {"a", "b"}}
    hum_groups = {"strong": {"python"}, "weak": set(), "missing": {"b", "c"}}
    per_group = [prf(sys_groups, hum_groups, group=g)
                 for g in ("strong", "weak", "missing")]
    f1s = [f for _, _, f in per_group]
    # strong:1.0 / weak:空vs空→1.0 / missing:0.5 → macro = 2.5/3
    assert sum(f1s) / 3 == pytest.approx(2.5 / 3)


# ---- compute_metrics（汇总 + verdict + 对抗断言） ----

def _pair(sys_score, human_score, sys_groups, hum_groups):
    return {"system_score": sys_score, "human_score": human_score,
            "system_groups": sys_groups, "human_groups": hum_groups}


def test_compute_metrics_aggregates():
    pairs = [
        _pair(80, 75, {"strong": {"a"}, "weak": set(), "missing": set()},
              {"strong": {"a"}, "weak": set(), "missing": set()}),
        _pair(20, 30, {"strong": set(), "weak": set(), "missing": {"a"}},
              {"strong": set(), "weak": set(), "missing": {"a"}}),
    ]
    m = compute_metrics(pairs)
    assert m["sample_size"] == 2
    assert m["spearman"] == pytest.approx(1.0)
    assert m["mae"] == pytest.approx(7.5)
    assert m["jaccard"] == pytest.approx(1.0)
    assert m["prf_micro"]["f1"] == pytest.approx(1.0)
    assert m["prf_missing"]["f1"] == pytest.approx(1.0)
    assert m["verdict"] == "pass"


def test_verdict_thresholds():
    """阈值表判定：ρ/MAE/F1 三者最差档决定 verdict。"""
    good = [{"system_score": i, "human_score": i,
             "system_groups": g, "human_groups": g}
            for i, g in enumerate([{"strong": {"a"}, "weak": set(),
                                    "missing": set()}] * 5)]
    assert compute_metrics(good)["verdict"] == "pass"
    # MAE 恶化到 block 档（>20）
    bad = [{"system_score": s + 40, "human_score": s,
            "system_groups": g, "human_groups": g}
           for s, g in enumerate([{"strong": {"a"}, "weak": set(),
                                   "missing": set()}] * 5)]
    assert compute_metrics(bad)["verdict"] == "block"


def test_adversarial_assertions_reported():
    """对抗三用例结果聚合进报告（分差/上界/三组一致）。"""
    pairs = [
        # 对抗 1：同 JD conf 高低两画像（e2-001 vs e2-002 模式）
        _pair(70, 55, {"strong": {"a"}, "weak": set(), "missing": set()},
              {"strong": {"a"}, "weak": set(), "missing": set()}),
        _pair(40, 35, {"strong": set(), "weak": {"a"}, "missing": set()},
              {"strong": set(), "weak": {"a"}, "missing": set()}),
        # 对抗 2：无关 JD
        _pair(18, 25, {"strong": set(), "weak": set(), "missing": {"x"}},
              {"strong": set(), "weak": set(), "missing": {"x"}}),
        # 对抗 3：别名变体对（三组一致 + 分数一致）
        _pair(62, 62, {"strong": {"b"}, "weak": set(), "missing": {"y"}},
              {"strong": {"b"}, "weak": set(), "missing": {"y"}}),
        _pair(62, 62, {"strong": {"b"}, "weak": set(), "missing": {"y"}},
              {"strong": {"b"}, "weak": set(), "missing": {"y"}}),
    ]
    m = compute_metrics(pairs, adversarial={
        "bare_claim_pair": (70, 40), "unrelated_upper": 29,
        "alias_pair": (62, 62)})
    adv = m["adversarial"]
    assert adv["bare_claim_gap"] >= 10            # 裸声明分差显著
    assert adv["unrelated_scores_max"] <= 29      # 无关 JD 分数上界
    assert adv["alias_scores_equal"] is True      # 别名变体分数一致


def test_thresholds_frozen():
    assert E2_THRESHOLDS == {
        "spearman": {"pass": 0.7, "warn": 0.5},
        "mae": {"pass": 12, "warn": 20},
        "jaccard": {"pass": 0.7, "warn": 0.5},
        "prf": {"pass": 0.7, "warn": 0.5},
    }
