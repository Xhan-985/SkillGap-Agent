"""Match 服务层（Phase 7，API §2.8）。

装配：job_skill（要求侧，required_level 复用 gap-v1 单一事实来源）
+ candidate_skill（画像侧）+ 双方软性数据 → scoring 纯函数 →
解释（模板默认 / LLM 可选+一致性校验）→ match_result 落库。

零 LLM 红线：分数路径纯 SQL + 纯函数（D8 守卫）；LLM 仅解释文本。
"""
from __future__ import annotations

import json

from psycopg.types.json import Json

from skillgap.gap.gapcalc import required_level as _required_level
from skillgap.match.explanation import (
    check_consistency, generate_llm_explanation, render_template,
)
from skillgap.match.scoring import compute_match


class CandidateNotFound(LookupError):
    """candidate_id 不存在。"""


class JobNotFound(LookupError):
    """job_id 不存在。"""


class ExplanationInconsistency(RuntimeError):
    """LLM 解释数字与 breakdown 不一致（校验器拦截，调用方应降级）。"""


def match_score(conn, candidate_id: int, job_id: int, *,
                explain_llm: bool = False, gateway=None) -> dict:
    """(画像, 岗位) → 匹配结果（API §2.8 结构）+ 落库 match_result。"""
    with conn.cursor() as cur:
        cur.execute("SELECT id, soft_profile FROM candidate WHERE id = %s",
                    (candidate_id,))
        cand = cur.fetchone()
        if cand is None:
            raise CandidateNotFound(f"candidate {candidate_id} 不存在")
        cur.execute("SELECT id, soft_requirements FROM job WHERE id = %s",
                    (job_id,))
        job = cur.fetchone()
        if job is None:
            raise JobNotFound(f"job {job_id} 不存在")
        cur.execute(
            """SELECT s.canonical_name AS name, js.importance, js.intensity
               FROM job_skill js JOIN skill s ON s.id = js.skill_id
               WHERE js.job_id = %s ORDER BY js.id""",
            (job_id,))
        req_rows = cur.fetchall()
        cur.execute(
            """SELECT s.canonical_name AS name, cs.level, cs.confidence
               FROM candidate_skill cs JOIN skill s ON s.id = cs.skill_id
               WHERE cs.candidate_id = %s""",
            (candidate_id,))
        act_rows = cur.fetchall()

    reqs = [{"skill": r["name"], "importance": r["importance"],
             "required_level": _required_level(r["importance"],
                                               r["intensity"])}
            for r in req_rows]
    actual = {r["name"]: {"level": r["level"],
                          "confidence": float(r["confidence"])}
              for r in act_rows}
    soft_pair = {"jd": job["soft_requirements"] or [],
                 "candidate": cand["soft_profile"] or {}}

    result = compute_match(reqs, actual, soft_pair)

    if explain_llm and gateway is not None:
        try:
            explanation = generate_llm_explanation(gateway, result)
            bad = check_consistency(explanation, result)
            if bad:
                raise ExplanationInconsistency(
                    f"LLM 解释含不一致数字: {bad}")
        except ExplanationInconsistency:
            raise
        except Exception:
            explanation = render_template(result)   # LLM 失败 → 降级模板
    else:
        explanation = render_template(result)
    result["explanation"] = explanation

    _persist(conn, candidate_id, job_id, result)
    return result


def _persist(conn, candidate_id: int, job_id: int, result: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO match_result
               (candidate_id, job_id, overall_score, breakdown,
                strong_skills, weak_skills, missing_skills, explanation,
                scoring_version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (candidate_id, job_id, result["overall_score"],
             Json(result["breakdown"]),
             Json(result["strong_skills"]), Json(result["weak_skills"]),
             Json(result["missing_skills"]), result["explanation"],
             result["scoring_version"]))
    conn.commit()
