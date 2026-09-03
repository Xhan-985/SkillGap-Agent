"""Phase 8 roi 纯函数单测（DATA_MODEL §4 冻结公式：potential_gain =
Demand×Gap÷Cost；M9 验收：数值 100% 公式计算）。口径见
docs/plans/2026-09-03-phase8-recommendation.md D1-D6。"""
from pathlib import Path

import pytest

from skillgap.recommend.roi import (
    COST_VALUE, MIN_FREQUENCY, ROI_VERSION, TOP_K, compute_priority,
    potential_gain, render_rationale,
)

SRC = (Path(__file__).resolve().parents[1] / "src" / "skillgap"
       / "recommend" / "roi.py")


def _item(skill, frequency, gap, cost, **kw):
    return {"skill": skill, "frequency": frequency, "gap": gap,
            "cost": cost, "sample_size": 100,
            "evidence_ref": {"snapshot_id": 4}, "type": "genuine",
            **kw}


# ---- potential_gain ----

def test_potential_gain_formula():
    assert potential_gain(0.5, 3, "low") == pytest.approx(1.5)   # 0.5×3÷1
    assert potential_gain(0.5, 3, "mid") == pytest.approx(0.75)   # ÷2
    assert potential_gain(0.5, 3, "high") == pytest.approx(0.5)   # ÷3


def test_potential_gain_zero_cases():
    assert potential_gain(0.0, 3, "low") == 0.0       # 无需求 → 0
    assert potential_gain(0.5, 0, "low") == 0.0       # 无缺口 → 0
    assert potential_gain(0.5, 0, "high") == 0.0      # 零缺口不除成本爆错


def test_cost_value_frozen():
    assert COST_VALUE == {"low": 1.0, "mid": 2.0, "high": 3.0}
    assert MIN_FREQUENCY == 0.20
    assert TOP_K == 10
    assert ROI_VERSION == "roi-v1"


# ---- compute_priority ----

def test_compute_priority_orders_by_potential_gain():
    items = [
        _item("docker", 0.5, 1, "high"),     # 0.5×1÷3 ≈ 0.17
        _item("mcp", 0.4, 3, "low"),         # 0.4×3÷1 = 1.2 ← 最高
        _item("langgraph", 0.3, 2, "low"),    # 0.3×2÷1 = 0.6
    ]
    out = compute_priority(items)
    assert [x["skill"] for x in out] == ["mcp", "langgraph", "docker"]
    assert out[0]["potential_gain"] == pytest.approx(1.2)
    assert out[0]["formula_version"] == ROI_VERSION


def test_compute_priority_tie_breaks_by_frequency():
    """同分按 frequency 降序（D1）。"""
    items = [
        _item("a", 0.2, 3, "high"),     # 0.2
        _item("b", 0.4, 1, "low"),      # 0.4×1÷1=0.4 —— 不同分对照
        _item("c", 0.6, 1, "low"),      # 0.6 —— 与谁都不平，改构造平分
    ]
    # 直接构造平分对：0.6×2÷2=0.6 vs 0.3×2÷1=0.6
    items = [
        _item("x", 0.6, 2, "mid"),      # 0.6
        _item("y", 0.3, 2, "low"),      # 0.6
    ]
    out = compute_priority(items)
    assert [x["skill"] for x in out] == ["x", "y"]   # 频次高者优先


def test_compute_priority_filters_low_frequency():
    items = [
        _item("hot", 0.5, 3, "low"),
        _item("cold", 0.19, 3, "low"),       # 频次 <0.20 → 不入清单
    ]
    out = compute_priority(items)
    assert [x["skill"] for x in out] == ["hot"]


def test_compute_priority_zero_gap_excluded():
    """已达标（gap=0）技能不入优先级（无提升空间）。"""
    items = [
        _item("gapless", 0.8, 0, "low"),
        _item("gapful", 0.5, 2, "low"),
    ]
    out = compute_priority(items)
    assert [x["skill"] for x in out] == ["gapful"]


def test_compute_priority_top_k_truncates():
    items = [_item(f"s{i}", 0.9, 5, "low") for i in range(15)]
    out = compute_priority(items)
    assert len(out) == TOP_K == 10


def test_compute_priority_transfers_type():
    """transferable 标注透传（D2：rationale 需注明可迁移）。"""
    out = compute_priority([_item("java", 0.5, 1, "low",
                                 type="transferable")])
    assert out[0]["type"] == "transferable"


def test_compute_priority_sample_insufficient_flag():
    """sample_size<30 → SAMPLE_INSUFFICIENT（demand 缺省明示，不臆造）。"""
    out = compute_priority([_item("thin", 0.5, 2, "low", sample_size=12)])
    assert out[0]["demand_status"] == "SAMPLE_INSUFFICIENT"
    # 薄样本仍计算但不隐藏标记
    assert out[0]["potential_gain"] == pytest.approx(1.0)


def test_compute_priority_empty():
    assert compute_priority([]) == []


# ---- render_rationale（D3：模板，数字全部来自 item 字段） ----

def test_render_rationale_numbers_from_item():
    item = compute_priority([_item("mcp", 0.4, 3, "low")])[0]
    budget = 14
    text = render_rationale(item, time_budget_days=budget)
    assert "mcp" in text
    # 数字一致性：解释数字 ⊆ item 派生集（复用 Phase 7 校验思路）
    import re
    nums = {float(x) for x in re.findall(r"\d+(?:\.\d+)?", text)}
    allowed = {item["frequency"], item["potential_gain"],
               float(item["gap"]), COST_VALUE[item["cost"]],
               float(item["gap"]) * 100, item["frequency"] * 100,
               float(item["sample_size"]), float(budget)}
    assert nums <= allowed


def test_render_rationale_transferable_note():
    item = compute_priority([_item("java", 0.5, 1, "low",
                                  type="transferable")])[0]
    text = render_rationale(item, time_budget_days=14)
    assert "迁移" in text            # D2：注明已有相邻证据


def test_render_rationale_budget_mention():
    item = compute_priority([_item("mcp", 0.4, 3, "low")])[0]
    assert "14" in render_rationale(item, time_budget_days=14)


# ---- 守卫（D6：零 skillgap 依赖 + 零 LLM） ----

def test_no_skillgap_dependency_guard():
    src = SRC.read_text(encoding="utf-8")
    assert "import skillgap" not in src
    assert "from skillgap" not in src
    assert "llm" not in src.lower()
