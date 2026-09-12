"""Match Score 纯函数（Phase 7，DATA_MODEL §4.1/§4.3 冻结公式）。

Overall = 100 × (0.45×coverage + 0.25×importance_coverage
           + 0.20×evidence_quality + 0.10×experience_relevance)

口径（docs/plans/2026-09-03-phase7-job-matching.md D1-D8，DECISION_LOG
C1/C2 裁决）：
- 满足 ⇔ actual_level ≥ required_level（conf_factor 只折减贡献不改满足性
  ——与 gap 的 confidence 不进 gap 互补，H1 修复两面）
- 三组：missing ⇔ 无记录；strong ⇔ 满足 ∧ conf ≥ 0.5；weak ⇔ 其余
- 除零守卫按 §4.3 中性 0.5；neutral_flags 明示
- 真实库 JD soft_requirements 全空（C1）→ experience_relevance 恒中性

规则计算非 LLM（M6 红线）：本模块零 skillgap 依赖，守卫测试锁定。
版本 1.0.0——权重/阈值/三组规则任一变更升 patch 并重跑 E2。
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

SCORING_VERSION = "1.0.0"

WEIGHTS = {"coverage": 0.45, "importance_coverage": 0.25,
           "evidence_quality": 0.20, "experience_relevance": 0.10}
REQUIRED_WEIGHT = {"must_have": 3.0, "nice_to_have": 1.0}
EVIDENCE_THRESHOLD = 0.5      # strong 判定线（与 gap-v1 同源）
NEUTRAL = 0.5


def conf_factor(confidence: float) -> float:
    """证据充分的技能贡献更高（§4.1）。"""
    return 0.5 + 0.5 * confidence


def compute_match(reqs: Sequence[Mapping], actual: Mapping[str, Mapping],
                  soft_pair: Mapping | None) -> dict:
    """(JD 要求侧, 画像侧, 软性对) → 匹配结果（纯函数）。

    reqs:  [{skill, importance, required_level}]
    actual: {skill: {level, confidence}}——无该键 = 画像无记录
    soft_pair: {"jd": [{type, value}], "candidate": {...}} 或 None
    """
    strong: list[str] = []
    weak: list[str] = []
    missing: list[str] = []
    neutral_flags: list[str] = []

    total_req_w = 0.0
    ach_w = 0.0
    must_total = 0.0
    must_satisfied = 0.0
    matched_confs: list[float] = []

    for r in reqs:
        skill = r["skill"]
        w = REQUIRED_WEIGHT[r["importance"]]
        total_req_w += w
        if r["importance"] == "must_have":
            must_total += w
        rec = actual.get(skill)
        if rec is None:
            missing.append(skill)
            continue
        matched_confs.append(float(rec["confidence"]))
        satisfied = rec["level"] >= r["required_level"]
        if satisfied:
            ach_w += w * conf_factor(float(rec["confidence"]))
            if r["importance"] == "must_have":
                must_satisfied += w
            if float(rec["confidence"]) >= EVIDENCE_THRESHOLD:
                strong.append(skill)
            else:
                weak.append(skill)       # 等级达标但证据薄
        else:
            weak.append(skill)

    if total_req_w == 0:
        coverage = 0.0
        neutral_flags.append("no_skills_required")
        invalid = "no_skills"
    else:
        coverage = ach_w / total_req_w
        invalid = None
    if must_total == 0:
        importance_coverage = NEUTRAL
        neutral_flags.append("no_must_have")
    else:
        importance_coverage = must_satisfied / must_total
    if matched_confs:
        evidence_quality = sum(matched_confs) / len(matched_confs)
    else:
        evidence_quality = NEUTRAL
        neutral_flags.append("no_matched_skills")
    experience_relevance = _experience_relevance(soft_pair, neutral_flags)

    overall = 100.0 * (WEIGHTS["coverage"] * coverage
                       + WEIGHTS["importance_coverage"] * importance_coverage
                       + WEIGHTS["evidence_quality"] * evidence_quality
                       + WEIGHTS["experience_relevance"]
                       * experience_relevance)
    return {
        "overall_score": round(overall, 1),
        "scoring_version": SCORING_VERSION,
        "breakdown": {"coverage": round(coverage, 4),
                      "importance_coverage": round(importance_coverage, 4),
                      "evidence_quality": round(evidence_quality, 4),
                      "experience_relevance":
                          round(experience_relevance, 4)},
        "strong_skills": strong,
        "weak_skills": weak,
        "missing_skills": missing,
        "neutral_flags": neutral_flags,
        "invalid": invalid,
    }


def _experience_relevance(soft_pair: Mapping | None,
                          neutral_flags: list[str]) -> float:
    """软性要求（年限/学历/语言）逐项匹配率（§4.1）。

    可评估项为 0（JD 侧无 soft_requirements / 候选侧缺失）→ 0.5 中性
    （§4.3；真实库 JD 全空——DECISION_LOG C1，恒走本分支）。
    """
    if not soft_pair:
        neutral_flags.append("soft_not_evaluable")
        return NEUTRAL
    jd_soft = list(soft_pair.get("jd") or [])
    cand = soft_pair.get("candidate") or {}
    if not jd_soft:
        neutral_flags.append("soft_not_evaluable")
        return NEUTRAL
    results = []
    for item in jd_soft:
        ok = _soft_item_matches(item, cand)
        if ok is None:
            continue          # 不可评估项不计入分母
        results.append(ok)
    if not results:
        neutral_flags.append("soft_not_evaluable")
        return NEUTRAL
    return sum(results) / len(results)


def _soft_item_matches(item: Mapping, cand: Mapping) -> bool | None:
    """单项软性匹配：True/False/None（不可评估）。"""
    t = item.get("type")
    v = str(item.get("value") or "")
    if t == "experience":
        years = cand.get("experience_years")
        if isinstance(years, dict):
            # soft_profile 存储结构 {value, evidence_text}（profile/service
            # _soft_profile_json）——取裸值参与比较（T4 修复：原先 dict>=int 必崩，
            # 真实库 JD soft 全空从未触发；非公式变更，SCORING_VERSION 不动）
            years = years.get("value")
        if years is None:
            return None
        need = _parse_years(v)
        return years >= need if need is not None else None
    if t == "education":
        edu = cand.get("education")
        if not edu:
            return None
        for level, names in (("博士", ("博士",)), ("硕士", ("硕士", "研究生")),
                             ("本科", ("本科", "学士", "大学"))):
            if any(n in v for n in names):
                # JD 要求 level，候选学历文本需达到该档
                rank = {"博士": 3, "硕士": 2, "本科": 1}
                cand_rank = 0
                for lv, nms in (("博士", ("博士",)), ("硕士", ("硕士", "研究生")),
                                ("本科", ("本科", "学士", "大学"))):
                    if any(n in str(edu) for n in nms):
                        cand_rank = rank[lv]
                        break
                return cand_rank >= rank[level]
        return None
    if t == "language":
        langs = cand.get("languages")
        if not langs:
            return None
        # 粗粒度：JD 要求语种在候选语言文本中出现即匹配
        tokens = [tok for tok in ("英语", " CET-6", " CET-4", "英语六级",
                                  "英语四级") if tok.strip() in str(langs)]
        return any(tok in v for tok in ("英语", "CET")) and bool(tokens or
                                                                "英语" in str(langs))
    return None


def _parse_years(v: str) -> int | None:
    """'3年以上'/'3-5年' → 下限年数；解析失败 None。"""
    import re
    m = re.search(r"(\d+)", v)
    return int(m.group(1)) if m else None


def breakdown_numbers(result: Mapping) -> set[float]:
    """breakdown 派生数字全集（解释一致性校验的对照集——explanation.py 用）。

    含四维原始值、总分、以及乘以 100 的百分比值（解释常写"45%"式）。
    """
    nums = {round(float(result["overall_score"]), 1)}
    for v in result["breakdown"].values():
        nums.add(round(float(v), 4))
        nums.add(round(float(v) * 100, 1))
    return nums
