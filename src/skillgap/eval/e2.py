"""E2 评测器（岗位匹配质量回归——EVALUATION_PLAN §3）。

口径（预声明，跑分前冻结——§3.2/§3.3）：
- 指标：Spearman ρ（平均秩 + Pearson，手写无 scipy）、MAE、三组 Jaccard、
  micro P/R/F1（池化三组 (对,技能) 决策）+ **Missing 组单独主报** +
  macro F1（低频组不隐身）
- 阈值：pass/warn/block 同表——ρ ≥0.7/0.5、MAE ≤12/20、Jaccard ≥0.7/0.5、
  F1 ≥0.7/0.5；verdict 取各指标最差档
- 对抗三用例聚合：裸声明分差 ≥10 / 无关 JD 上界 ≤29 / 别名变体分数一致
- 红线：LLM 不参与指标计算（§1.2）；系统分由 match.scoring 纯函数产出
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

E2_THRESHOLDS = {
    "spearman": {"pass": 0.7, "warn": 0.5},
    "mae": {"pass": 12, "warn": 20},
    "jaccard": {"pass": 0.7, "warn": 0.5},
    "prf": {"pass": 0.7, "warn": 0.5},
}
GROUPS = ("strong", "weak", "missing")


# ---- 基础指标（纯函数） ----

def _average_ranks(values: Sequence[float]) -> list[float]:
    """并列取平均秩（Spearman 标准处理）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1            # 1-based 平均秩
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """秩相关（Pearson on 平均秩）。常数序列 / 空输入 → 0.0。"""
    n = len(x)
    if n < 2 or n != len(y):
        return 0.0
    rx, ry = _average_ranks(list(x)), _average_ranks(list(y))
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den_x = sum((a - mx) ** 2 for a in rx)
    den_y = sum((b - my) ** 2 for b in ry)
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y) ** 0.5


def mae(system: Sequence[float], human: Sequence[float]) -> float:
    return sum(abs(a - b) for a, b in zip(system, human)) / len(system)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0        # 双空 = 完全一致
    return len(a & b) / len(a | b)


def prf(system_groups: Mapping[str, set],
        human_groups: Mapping[str, set],
        group: str | None = None) -> tuple[float, float, float]:
    """(precision, recall, f1)——group=None 池化三组，否则单组。

    双空 = 完全一致（与 jaccard 约定对齐）→ (1.0, 1.0, 1.0)。
    """
    keys = [group] if group else list(GROUPS)
    sys_items = {(k, s) for k in keys
                 for s in system_groups.get(k, set())}
    hum_items = {(k, s) for k in keys
                 for s in human_groups.get(k, set())}
    return _prf_from_sets(sys_items, hum_items)


def _prf_from_sets(sys_set: set, hum_set: set) -> tuple[float, float, float]:
    tp = len(sys_set & hum_set)
    if not sys_set and not hum_set:
        return 1.0, 1.0, 1.0
    p = tp / len(sys_set) if sys_set else 1.0
    r = tp / len(hum_set) if hum_set else 1.0
    f1 = 2 * p * r / (p + r) if tp else 0.0
    return p, r, f1


# ---- 汇总 + verdict ----

def _grade(value: float, table: Mapping[str, float],
           higher_better: bool = True) -> str:
    if higher_better:
        if value >= table["pass"]:
            return "pass"
        if value >= table["warn"]:
            return "warn"
        return "block"
    if value <= table["pass"]:
        return "pass"
    if value <= table["warn"]:
        return "warn"
    return "block"


def compute_metrics(pairs: Sequence[Mapping],
                    adversarial: Mapping | None = None) -> dict:
    """pairs: [{system_score, human_score, system_groups, human_groups}]。

    micro 池化 (对, 组, 技能) 三元组决策——不同对的同名技能各计一次
    （与 E1 的跨样本池化口径一致）；macro 逐组平均。
    adversarial（可选）：{"bare_claim_pair": (hi, lo), "unrelated_upper": U,
    "alias_pair": (a, b)}——对抗用例断言原料。
    """
    sys_scores = [p["system_score"] for p in pairs]
    hum_scores = [p["human_score"] for p in pairs]
    rho = spearman(sys_scores, hum_scores)
    mean_abs = mae(sys_scores, hum_scores)
    jac = sum(jaccard(p["system_groups"].get(g, set()),
                      p["human_groups"].get(g, set()))
              for p in pairs for g in GROUPS) / (len(pairs) * len(GROUPS))

    sys_items = {(i, g, s) for i, p in enumerate(pairs)
                 for g in GROUPS for s in p["system_groups"].get(g, set())}
    hum_items = {(i, g, s) for i, p in enumerate(pairs)
                 for g in GROUPS for s in p["human_groups"].get(g, set())}

    micro = _prf_from_sets(sys_items, hum_items)
    missing = _prf_from_sets({t for t in sys_items if t[1] == "missing"},
                             {t for t in hum_items if t[1] == "missing"})
    macro_f1 = sum(
        _prf_from_sets({t for t in sys_items if t[1] == g},
                       {t for t in hum_items if t[1] == g})[2]
        for g in GROUPS) / len(GROUPS)

    out = {
        "sample_size": len(pairs),
        "spearman": round(rho, 4),
        "mae": round(mean_abs, 2),
        "jaccard": round(jac, 4),
        "prf_micro": {"precision": round(micro[0], 4),
                      "recall": round(micro[1], 4),
                      "f1": round(micro[2], 4)},
        "prf_missing": {"precision": round(missing[0], 4),
                        "recall": round(missing[1], 4),
                        "f1": round(missing[2], 4)},
        "macro_f1": round(macro_f1, 4),
    }

    grades = [_grade(rho, E2_THRESHOLDS["spearman"]),
             _grade(mean_abs, E2_THRESHOLDS["mae"], higher_better=False),
             _grade(jac, E2_THRESHOLDS["jaccard"]),
             _grade(micro[2], E2_THRESHOLDS["prf"])]
    out["verdict"] = ("block" if "block" in grades else
                      "warn" if "warn" in grades else "pass")

    if adversarial:
        hi, lo = adversarial["bare_claim_pair"]
        out["adversarial"] = {
            "bare_claim_gap": round(hi - lo, 1),
            "bare_claim_ok": hi - lo >= 10,
            "unrelated_scores_max": adversarial.get(
                "unrelated_scores_max", 0.0),
            "unrelated_ok": adversarial.get("unrelated_scores_max",
                                            0.0) <= adversarial.get(
                                                "unrelated_upper", 29),
            "alias_scores_equal": bool(
                adversarial["alias_pair"][0] == adversarial["alias_pair"][1]),
        }
    return out
