"""Phase 7 scoring 纯函数单测（DATA_MODEL §4.1/§4.3 冻结公式；ROADMAP
验收：单调性 100%、conf 折减对抗性、三组判定、中性守卫）。口径见
docs/plans/2026-09-03-phase7-job-matching.md D1-D8。"""
from pathlib import Path

import pytest

from skillgap.match.scoring import (
    EVIDENCE_THRESHOLD, REQUIRED_WEIGHT, SCORING_VERSION, WEIGHTS,
    compute_match, conf_factor,
)

SRC = (Path(__file__).resolve().parents[1] / "src" / "skillgap"
       / "match" / "scoring.py")


def _req(skill, importance="must_have", required_level=3):
    return {"skill": skill, "importance": importance,
            "required_level": required_level}


def _act(level, confidence):
    return {"level": level, "confidence": confidence}


# ---- conf_factor ----

def test_conf_factor_bounds():
    assert conf_factor(0.0) == 0.5
    assert conf_factor(1.0) == 1.0
    assert conf_factor(0.6) == pytest.approx(0.8)


# ---- coverage ----

def test_coverage_weights_and_satisfaction():
    """must=3/nice=1 权重；满足才计入；conf_factor 折减贡献。"""
    r = compute_match(
        [_req("python", required_level=3), _req("docker", required_level=3)],
        {"python": _act(4, 1.0)}, None)
    # ach = 3×1.0；req = 3+3 → coverage = 0.5
    assert r["breakdown"]["coverage"] == pytest.approx(0.5)
    assert r["missing_skills"] == ["docker"]


def test_coverage_conf_factor_discount():
    """D3：等级达标但 conf 低 → 满足（进 strong/weak 逻辑）但贡献打折。"""
    r_hi = compute_match([_req("python", required_level=3)],
                          {"python": _act(4, 1.0)}, None)
    r_lo = compute_match([_req("python", required_level=3)],
                          {"python": _act(4, 0.0)}, None)
    # ach_hi = 3×1.0 = 3；ach_lo = 3×0.5 = 1.5；req = 3
    assert r_hi["breakdown"]["coverage"] == pytest.approx(1.0)
    assert r_lo["breakdown"]["coverage"] == pytest.approx(0.5)


def test_coverage_nice_weight_one():
    r = compute_match(
        [_req("git", importance="nice_to_have", required_level=2)],
        {"git": _act(2, 1.0)}, None)
    assert r["breakdown"]["coverage"] == pytest.approx(1.0)


# ---- importance_coverage ----

def test_importance_coverage_must_only():
    r = compute_match(
        [_req("python", required_level=3), _req("git", "nice_to_have", 2),
         _req("docker", required_level=4)],
        {"python": _act(3, 1.0)},          # docker 不满足
        None)
    # must 满足 3 / must 总 6 = 0.5；nice 不参与
    assert r["breakdown"]["importance_coverage"] == pytest.approx(0.5)


def test_importance_coverage_neutral_when_no_must():
    """§4.3：无 must → 0.5 中性 + neutral_flags（e2-024 场景）。"""
    r = compute_match(
        [_req("mysql", "nice_to_have", required_level=2)],
        {"mysql": _act(4, 1.0)}, None)
    assert r["breakdown"]["importance_coverage"] == 0.5
    assert "no_must_have" in r["neutral_flags"]


# ---- evidence_quality ----

def test_evidence_quality_mean_of_matched():
    r = compute_match(
        [_req("python", required_level=3), _req("docker", required_level=5)],
        {"python": _act(3, 0.8),           # matched（有记录）
         "docker": _act(2, 0.4)},          # matched（有记录，不满足）
        None)
    assert r["breakdown"]["evidence_quality"] == pytest.approx(0.6)


def test_evidence_quality_neutral_when_no_match():
    r = compute_match([_req("docker", required_level=3)], {}, None)
    assert r["breakdown"]["evidence_quality"] == 0.5
    assert "no_matched_skills" in r["neutral_flags"]


# ---- experience_relevance（C1：完整逻辑 + 中性守卫） ----

def test_experience_relevance_full_match():
    soft = {"jd": [{"type": "experience", "value": "3年以上"},
                   {"type": "education", "value": "本科"},
                   {"type": "language", "value": "英语 CET-6"}],
            "candidate": {"experience_years": 4, "education": "本科·软件工程",
                          "languages": "CET-6"}}
    r = compute_match([_req("python", required_level=3)],
                      {"python": _act(3, 1.0)}, soft)
    assert r["breakdown"]["experience_relevance"] == 1.0


def test_experience_relevance_partial():
    soft = {"jd": [{"type": "experience", "value": "3年以上"},
                   {"type": "education", "value": "硕士"}],
            "candidate": {"experience_years": 4, "education": "本科·软件工程",
                          "languages": None}}
    # 年限达标、学历不符 → 0.5
    r = compute_match([_req("python", required_level=3)],
                      {"python": _act(3, 1.0)}, soft)
    assert r["breakdown"]["experience_relevance"] == pytest.approx(0.5)


def test_experience_relevance_neutral_when_jd_soft_missing():
    """C1：真实库 JD soft_requirements 全空 → 恒中性 0.5。"""
    r = compute_match([_req("python", required_level=3)],
                      {"python": _act(3, 1.0)}, None)
    assert r["breakdown"]["experience_relevance"] == 0.5
    assert "soft_not_evaluable" in r["neutral_flags"]


# ---- overall ----

def test_overall_full_marks():
    r = compute_match([_req("python", required_level=3)],
                      {"python": _act(5, 1.0)},
                      {"jd": [{"type": "experience", "value": "3年以上"},
                              {"type": "education", "value": "本科"}],
                       "candidate": {"experience_years": 5,
                                     "education": "硕士·计算机",
                                     "languages": "CET-6"}})
    assert r["overall_score"] == pytest.approx(100.0)
    assert r["scoring_version"] == SCORING_VERSION == "1.0.0"


def test_overall_95_when_jd_soft_empty():
    """JD 软性数组为空 → 中性 0.5（C1 真实库场景）→ 上限 95。"""
    r = compute_match([_req("python", required_level=3)],
                      {"python": _act(5, 1.0)},
                      {"jd": [], "candidate": {"experience_years": 5}})
    assert r["overall_score"] == pytest.approx(95.0)


def test_overall_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0)
    assert REQUIRED_WEIGHT == {"must_have": 3.0, "nice_to_have": 1.0}


def test_overall_zero_when_nothing_matches():
    r = compute_match([_req("docker", required_level=3)], {}, None)
    # coverage=0, imp=0, evq=0.5, exp=0.5 → 0.45*0 + 0.25*0 + 0.2*0.5
    # + 0.1*0.5 = 15
    assert r["overall_score"] == pytest.approx(15.0)


# ---- 单调性（M6 验收：能力提升 → 分数不降） ----

def test_monotonic_in_level():
    scores = [compute_match(
        [_req("python", required_level=4)],
        {"python": _act(lv, 0.8)}, None)["overall_score"]
        for lv in range(1, 6)]
    assert all(a <= b for a, b in zip(scores, scores[1:]))


def test_monotonic_in_confidence():
    scores = [compute_match(
        [_req("python", required_level=4)],
        {"python": _act(4, cf)}, None)["overall_score"]
        for cf in (0.0, 0.3, 0.6, 1.0)]
    assert all(a <= b for a, b in zip(scores, scores[1:]))


# ---- 对抗性（§3.3 用例 1：裸声明折减） ----

def test_adversarial_bare_claim_scores_lower():
    """E2 e2-001 vs e2-002 锚点：同技能同等级，conf 1.0 vs 0.3 分差显著。"""
    reqs = [_req("python", required_level=3), _req("rag", required_level=3)]
    hi = compute_match(reqs, {"python": _act(3, 1.0),
                              "rag": _act(3, 1.0)}, None)["overall_score"]
    lo = compute_match(reqs, {"python": _act(3, 0.3),
                              "rag": _act(3, 0.3)}, None)["overall_score"]
    assert lo < hi
    assert hi - lo >= 10          # 显著分差（非噪声）


# ---- 三组判定（D4） ----

def test_three_group_classification():
    r = compute_match(
        [_req("python", required_level=3),      # 满足+证据 → strong
         _req("docker", required_level=5),       # 有记录不满足 → weak
         _req("git", required_level=3),          # 无记录 → missing
         _req("redis", required_level=3)],       # 满足但 conf<0.5 → weak
        {"python": _act(4, 0.9), "docker": _act(3, 0.9),
         "redis": _act(3, 0.3)},
        None)
    assert r["strong_skills"] == ["python"]
    assert set(r["weak_skills"]) == {"docker", "redis"}
    assert r["missing_skills"] == ["git"]      # redis 有记录不进 missing


def test_strong_requires_both_level_and_evidence():
    r = compute_match([_req("python", required_level=3)],
                      {"python": _act(4, EVIDENCE_THRESHOLD)}, None)
    assert r["strong_skills"] == ["python"]      # 恰好 0.5 达标
    r2 = compute_match([_req("python", required_level=3)],
                       {"python": _act(4, 0.49)}, None)
    assert r2["strong_skills"] == []
    assert r2["weak_skills"] == ["python"]


# ---- invalid / 空守卫（§4.3） ----

def test_invalid_when_no_skills_required():
    r = compute_match([], {"python": _act(3, 1.0)}, None)
    assert r["invalid"] == "no_skills"
    assert r["breakdown"]["coverage"] == 0.0
    assert "no_skills_required" in r["neutral_flags"]


# ---- 守卫（D8：零 skillgap 依赖 + 零 LLM） ----

def test_no_skillgap_dependency_guard():
    src = SRC.read_text(encoding="utf-8")
    assert "import skillgap" not in src
    assert "from skillgap" not in src
    assert "llm" not in src.lower().replace("零 llm", "").replace(
        "非 llm", "")


def test_version_frozen():
    assert SCORING_VERSION == "1.0.0"
    assert EVIDENCE_THRESHOLD == 0.5
