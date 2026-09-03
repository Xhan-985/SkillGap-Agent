"""Phase 6 gapcalc 纯函数单测（ROADMAP 验收：能力提升→缺口单调收窄；
完全达标/完全无关边界；genuine/transferable 判定）。口径见
docs/plans/2026-09-03-phase6-skill-gap.md D1-D3。"""
from pathlib import Path

import pytest

from skillgap.gap.gapcalc import (
    GAP_METHOD_VERSION, INTENSITY_LEVELS, classify, gap, required_level,
)

SRC = (Path(__file__).resolve().parents[1] / "src" / "skillgap"
       / "gap" / "gapcalc.py")


# ---- required_level（DATA_MODEL §4.2 映射） ----

@pytest.mark.parametrize("intensity,expected", [
    ("精通", 5), ("熟练", 4), ("熟悉", 3), ("了解", 2),
])
def test_required_level_must_have(intensity, expected):
    assert required_level("must_have", intensity) == expected


@pytest.mark.parametrize("intensity", ["精通", "熟练", "熟悉", "了解"])
def test_required_level_nice_to_have_capped_at_2(intensity):
    assert required_level("nice_to_have", intensity) == 2


def test_required_level_null_intensity():
    assert required_level("must_have", None) == 3    # 熟悉中性档（D1）
    assert required_level("nice_to_have", None) == 2


def test_required_level_invalid_inputs():
    with pytest.raises(ValueError):
        required_level("must_have", "掌握")           # 词表外程度词
    with pytest.raises(ValueError):
        required_level("optional", "精通")            # 词表外 importance


# ---- gap（D2：clamp 星级差；confidence 不进 gap——C1 裁决） ----

def test_gap_basic():
    assert gap(4, 1) == 3


def test_gap_clamped_at_zero():
    assert gap(2, 5) == 0
    assert gap(3, 3) == 0


def test_gap_full_when_absent():
    assert gap(5, 0) == 5                            # 无记录 → actual=0 全额缺口


def test_gap_monotonic_narrowing():
    """MVP M7 验收：能力提升 → 缺口单调收窄至 0。"""
    gaps = [gap(4, a) for a in range(6)]             # actual 0,1,2,3,4,5
    assert gaps == [4, 3, 2, 1, 0, 0]
    assert all(x >= y for x, y in zip(gaps, gaps[1:]))   # 单调非增


# ---- classify（D3：§4.4 冻结规则） ----

def _related(**overrides):
    m = {"python": {"python", "java"}, "java": {"java", "python"},
         "rag": {"rag"}, "postgres": {"postgres", "mysql"},
         "mysql": {"mysql", "postgres"}}
    m.update(overrides)
    return m


def test_classify_genuine_when_no_evidence_anywhere():
    out = classify({"java": 0.9}, _related(), ["rag"])
    assert out == {"rag": "genuine"}


def test_classify_transferable_via_relation():
    out = classify({"java": 0.9}, _related(), ["python"])
    assert out == {"python": "transferable"}


def test_classify_threshold_is_inclusive():
    """confidence ≥ 0.5 判 transferable（0.49 不达标 / 0.5 恰好达标）。"""
    assert classify({"java": 0.49}, _related(), ["python"]) == {
        "python": "genuine"}
    assert classify({"java": 0.5}, _related(), ["python"]) == {
        "python": "transferable"}


def test_classify_via_parent():
    related = {"langgraph": {"langgraph", "agent_framework"},
               "agent_framework": {"agent_framework"}}
    out = classify({"agent_framework": 0.8}, related, ["langgraph"])
    assert out == {"langgraph": "transferable"}


def test_classify_self_evidence_is_not_genuine():
    """缺口技能自身有 conf≥0.5 证据（level 不足仍有 gap）→ 非 genuine。"""
    out = classify({"rag": 0.6}, _related(), ["rag"])
    assert out == {"rag": "transferable"}


def test_classify_low_confidence_evidence_is_genuine():
    out = classify({"java": 0.3}, _related(), ["python"])
    assert out == {"python": "genuine"}


# ---- 守卫（D6：零 skillgap 依赖 + 版本冻结） ----

def test_no_skillgap_dependency_guard():
    """D6：零 skillgap 依赖（含 LLM 层），源码级静态锁定。"""
    src = SRC.read_text(encoding="utf-8")
    assert "import skillgap" not in src
    assert "from skillgap" not in src


def test_version_and_mapping_frozen():
    assert GAP_METHOD_VERSION == "gap-v1"
    assert INTENSITY_LEVELS == {"精通": 5, "熟练": 4, "熟悉": 3, "了解": 2}
