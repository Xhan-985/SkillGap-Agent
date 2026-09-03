"""Phase 5 confidence 纯函数单测（ROADMAP 验收：权重公式全覆盖，
含"熟悉 RAG"→低分边界）。逐例演算表见 docs/WEIGHT_RULES.md。"""
from pathlib import Path

from skillgap.profile.confidence import (
    CONFIDENCE_METHOD_VERSION, DECAY_FACTOR, EVIDENCE_WEIGHTS,
    compute_confidence,
)

SRC = (Path(__file__).resolve().parents[1] / "src" / "skillgap"
       / "profile" / "confidence.py")


def test_single_evidence_weights():
    assert compute_confidence([1.0]) == 1.0          # project_detail
    assert compute_confidence([0.6]) == 0.6          # project_desc
    assert compute_confidence([0.3]) == 0.3          # bare_claim（"熟悉 RAG"低分边界）
    assert compute_confidence([EVIDENCE_WEIGHTS["manual"]]) == 1.0


def test_decay_factor():
    assert compute_confidence([0.3, 0.3]) == 0.45
    assert compute_confidence([0.3, 0.3, 0.3]) == 0.525


def test_capped_at_one():
    assert compute_confidence([1.0, 0.3]) == 1.0
    assert compute_confidence([0.6, 0.6]) == 0.9
    assert compute_confidence([0.6, 0.6, 0.6]) == 1.0   # 1.05 截断


def test_order_independent():
    assert compute_confidence([0.3, 1.0]) == compute_confidence([1.0, 0.3])


def test_empty_is_zero():
    assert compute_confidence([]) == 0.0


def test_rounding_four_decimals():
    expected = round(0.3 * (1 + 0.5 + 0.25 + 0.125), 4)
    assert compute_confidence([0.3, 0.3, 0.3, 0.3]) == expected


def test_no_llm_dependency_guard():
    """自检红线：confidence 为规则计算非 LLM（源码级静态锁定）。"""
    src = SRC.read_text(encoding="utf-8")
    assert "skillgap.llm" not in src
    assert "skillgap.extract" not in src


def test_weights_match_db_check():
    """权重值域必须与 candidate_evidence.weight 的 DB CHECK 一致。"""
    assert set(EVIDENCE_WEIGHTS.values()) == {1.0, 0.6, 0.3}
    assert EVIDENCE_WEIGHTS == {
        "project_detail": 1.0, "project_desc": 0.6,
        "bare_claim": 0.3, "manual": 1.0,
    }
    assert DECAY_FACTOR == 0.5


def test_version_frozen():
    assert CONFIDENCE_METHOD_VERSION == "conf-v1"
