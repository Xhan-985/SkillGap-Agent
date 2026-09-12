"""Match 服务层（Phase 7，API §2.8；Phase 10 T4 增 jd_text 无状态模式）。

装配：job_skill（要求侧，required_level 复用 gap-v1 单一事实来源）
+ candidate_skill（画像侧）+ 双方软性数据 → scoring 纯函数 →
解释（模板默认 / LLM 可选+一致性校验）→ match_result 落库（仅 job_id 模式）。

jd_text 模式（Phase 10 C4）：LLM 无状态抽取 → 组装 reqs → 同一
compute_match 纯函数 → 不落库（无 consent 不入库——B1 纪律）；
与 job_id 模式无第二套公式（双模式一致性测试锚定）。

零 LLM 红线：分数路径纯 SQL + 纯函数（D8 守卫）；LLM 仅解释文本与
jd_text 模式的输入抽取（抽取是输入准备，不参与分数计算）。
"""
from __future__ import annotations

import json

from psycopg.types.json import Json

from skillgap.extract.analyzer import JDValidationError, MAX_LEN, MIN_LEN
from skillgap.gap.gapcalc import required_level as _required_level
from skillgap.ingest.extract import load_alias_map, resolve_skill_id
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
                explain_llm: bool = False, gateway=None,
                include_meta: bool = False) -> dict:
    """(画像, 岗位) → 匹配结果（API §2.8 结构）+ 落库 match_result。

    include_meta=True 附 _meta（reqs/actual/jd_text）——API 层组装 §2.8
    契约对象数组用（weak 成因/missing 溯源行号）；CLI 默认 False 输出不变。
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id, soft_profile FROM candidate WHERE id = %s",
                    (candidate_id,))
        cand = cur.fetchone()
        if cand is None:
            raise CandidateNotFound(f"candidate {candidate_id} 不存在")
        cur.execute("SELECT id, raw_text, soft_requirements FROM job "
                    "WHERE id = %s", (job_id,))
        job = cur.fetchone()
        if job is None:
            raise JobNotFound(f"job {job_id} 不存在")
        cur.execute(
            """SELECT s.canonical_name AS name, js.importance, js.intensity,
                      js.evidence_text
               FROM job_skill js JOIN skill s ON s.id = js.skill_id
               WHERE js.job_id = %s ORDER BY js.id""",
            (job_id,))
        req_rows = cur.fetchall()
        act_rows = _actual_rows(cur, candidate_id)

    reqs = [{"skill": r["name"], "importance": r["importance"],
             "required_level": _required_level(r["importance"],
                                               r["intensity"]),
             "evidence_text": r["evidence_text"]}
            for r in req_rows]
    actual = {r["name"]: {"level": r["level"],
                          "confidence": float(r["confidence"])}
              for r in act_rows}
    soft_pair = {"jd": job["soft_requirements"] or [],
                 "candidate": cand["soft_profile"] or {}}

    result = compute_match(reqs, actual, soft_pair)
    result["explanation"] = _explain(result, explain_llm, gateway)

    _persist(conn, candidate_id, job_id, result)
    if include_meta:
        result["_meta"] = {"reqs": reqs, "actual": actual,
                           "jd_text": job["raw_text"] or ""}
    return result


def match_score_text(conn, candidate_id: int, jd_text: str, extractor, *,
                     explain_llm: bool = False, gateway=None,
                     include_meta: bool = False) -> dict:
    """(画像, jd_text) → 匹配结果（Phase 10 C4；无状态，不落库）。

    抽取 → 词表归一 → 组装 reqs（与 job_id 模式同构）→ 同一 compute_match；
    词表外技能不进 reqs（记 _meta.unresolved，与管道 new_skill_candidate
    通道同语义）；无 consent 不入库——落库走 contribute 管道（B1）。
    """
    text = jd_text.strip()
    if not (MIN_LEN <= len(text) <= MAX_LEN):
        raise JDValidationError(
            f"jd_text 长度 {len(text)} 不在 [{MIN_LEN}, {MAX_LEN}]")

    with conn.cursor() as cur:
        cur.execute("SELECT soft_profile FROM candidate WHERE id = %s",
                    (candidate_id,))
        cand = cur.fetchone()
        if cand is None:
            raise CandidateNotFound(f"candidate {candidate_id} 不存在")
        act_rows = _actual_rows(cur, candidate_id)

    extraction = extractor.extract_full(text)
    alias_map = load_alias_map(conn)
    by_skill: dict[int, dict] = {}      # skill_id 去重（first-wins，
    unresolved: list[str] = []          # 对齐管道 ON CONFLICT DO NOTHING）
    for ann in extraction.skills:
        sid = resolve_skill_id(ann.raw_name, alias_map)
        if sid is None:
            unresolved.append(ann.raw_name)
            continue
        by_skill.setdefault(sid, {
            "skill": None,                   # canonical_name 批量回填
            "importance": ann.importance,
            "required_level": _required_level(ann.importance, ann.intensity),
            "evidence_text": ann.evidence_text})
    names = _canonical_names(conn, list(by_skill))
    reqs = []
    for sid, r in by_skill.items():
        r["skill"] = names[sid]
        reqs.append(r)
    actual = {r["name"]: {"level": r["level"],
                          "confidence": float(r["confidence"])}
              for r in act_rows}
    soft_pair = {"jd": [r.model_dump() for r in extraction.soft_requirements],
                 "candidate": cand["soft_profile"] or {}}

    result = compute_match(reqs, actual, soft_pair)
    result["explanation"] = _explain(result, explain_llm, gateway)
    if include_meta:
        result["_meta"] = {"reqs": reqs, "actual": actual, "jd_text": text,
                           "unresolved": unresolved}
    return result


def _actual_rows(cur, candidate_id: int) -> list:
    cur.execute(
        """SELECT s.canonical_name AS name, cs.level, cs.confidence
           FROM candidate_skill cs JOIN skill s ON s.id = cs.skill_id
           WHERE cs.candidate_id = %s""",
        (candidate_id,))
    return cur.fetchall()


def _canonical_names(conn, skill_ids: list[int]) -> dict[int, str]:
    if not skill_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, canonical_name FROM skill WHERE id = ANY(%s)",
                    (skill_ids,))
        return {r["id"]: r["canonical_name"] for r in cur.fetchall()}


def _explain(result: dict, explain_llm: bool, gateway) -> str:
    """模板默认 / LLM 可选（失败降级模板；数字不一致硬拦截向上抛）。"""
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
            return render_template(result)     # LLM 失败 → 降级模板
    return render_template(result)


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
