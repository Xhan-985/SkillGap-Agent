"""匹配 + 缺口端点（API.md §2.8 POST /api/match + §2.9 GET gaps）。

惰性 LLM 工厂：extractor/gateway 仅在 jd_text 模式 / explain=true 时
装配（job_id 模式零 LLM 红线——不因缺 key 而 502）。

契约组装（D3）：服务层三组是字符串列表（Phase 7 冻结结构），本层用
_meta（reqs/actual/jd_text）包装为 §2.8 对象数组：
- strong.evidence_ref=null（画像行号不落库——D2，与 §2.6 先例一致）
- weak.note 区分成因（等级达标但证据薄 / 等级未达标——查表填充非计算）
- missing.jd_evidence_ref="jd#L<n>"（JD 原文行号，尽力而为）

explain 降级口径（对齐 Phase 8 agent verify 先例）：LLM 叙事数字不一致
→ 拦截后降级确定性模板（数字仅由 breakdown 携带——UI_SPEC §2.4）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError
from skillgap.config import settings
from skillgap.gap.service import (
    CandidateNotFound as GapCandidateNotFound,
    GapQueryError, JobNotFound as GapJobNotFound, get_gaps,
)
from skillgap.ingest.normalize import JOB_CATEGORIES, canonicalize_for_hash
from skillgap.match.service import (
    CandidateNotFound, ExplanationInconsistency, JobNotFound,
    match_score, match_score_text,
)

router = APIRouter(tags=["match"])


class MatchRequest(BaseModel):
    candidate_id: int
    jd_text: str | None = None
    job_id: int | None = None
    explain: bool = False


def get_extractor_factory(conn=Depends(get_conn)):
    """惰性 JD 抽取器工厂（jd_text 模式调用时才装配 LLM）。"""
    def build():
        from skillgap.extract.llm_extractor import LLMSkillExtractor
        from skillgap.extract.prompt import PROMPT_VERSION
        from skillgap.llm.gateway import LLMGateway
        from skillgap.llm.provider import OpenAICompatibleProvider

        if not settings.llm_api_key:
            raise ApiError(502, "LLM_EXTRACTION_FAILED",
                           "服务端未配置 LLM_API_KEY，无法分析 JD 文本")
        provider = OpenAICompatibleProvider(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key,
            model=settings.llm_model, timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries)
        gateway = LLMGateway(conn, provider, PROMPT_VERSION)
        return LLMSkillExtractor(gateway)
    return build


def get_gateway_factory(conn=Depends(get_conn)):
    """惰性解释 gateway 工厂（explain=true 时才装配）。"""
    def build():
        from skillgap.extract.prompt import PROMPT_VERSION
        from skillgap.llm.gateway import LLMGateway
        from skillgap.llm.provider import OpenAICompatibleProvider

        if not settings.llm_api_key:
            raise ApiError(502, "LLM_TIMEOUT",
                           "服务端未配置 LLM_API_KEY，无法生成 LLM 解释")
        provider = OpenAICompatibleProvider(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key,
            model=settings.llm_model, timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries)
        return LLMGateway(conn, provider, PROMPT_VERSION)
    return build


@router.post("/api/match")
def match(body: MatchRequest,
          conn=Depends(get_conn),
          extractor_factory=Depends(get_extractor_factory),
          gateway_factory=Depends(get_gateway_factory)):
    """§2.8：jd_text / job_id 二选一；分数零 LLM，explain 叙事可选。"""
    from skillgap.extract.analyzer import JDValidationError
    from skillgap.extract.llm_extractor import ExtractionFailed
    from skillgap.llm.provider import LLMError

    if (body.jd_text is None) == (body.job_id is None):
        raise ApiError(422, "VALIDATION_ERROR",
                       "jd_text 与 job_id 必须二选一")

    def _run(explain: bool):
        gw = gateway_factory() if explain else None
        if body.jd_text is not None:
            return match_score_text(
                conn, body.candidate_id, body.jd_text,
                extractor_factory(), explain_llm=explain,
                gateway=gw, include_meta=True)
        return match_score(
            conn, body.candidate_id, body.job_id,
            explain_llm=explain, gateway=gw, include_meta=True)

    try:
        try:
            result = _run(body.explain)
        except ExplanationInconsistency:
            # LLM 叙事数字不一致被拦截 → 降级确定性模板重跑（数字仅由
            # breakdown 携带；纯函数毫秒级，服务层拦截语义不变）
            result = _run(False)
    except (CandidateNotFound, JobNotFound) as e:
        raise ApiError(404, "NOT_FOUND", str(e)) from e
    except JDValidationError as e:
        raise ApiError(422, "VALIDATION_ERROR", str(e)) from e
    except ExtractionFailed as e:
        raise ApiError(502, "LLM_EXTRACTION_FAILED",
                       str(e), {"retries": settings.llm_max_retries}) from e
    except LLMError as e:
        raise ApiError(502, "LLM_TIMEOUT", "LLM 上游调用失败",
                       {"cause": type(e).__name__}) from e
    return _to_contract(result)


def _to_contract(result: dict) -> dict:
    """服务层冻结结构 → §2.8 契约对象数组（查表填充，零公式）。"""
    meta = result.pop("_meta", {})
    reqs = {r["skill"]: r for r in meta.get("reqs", [])}
    actual = meta.get("actual", {})
    jd_text = meta.get("jd_text", "")

    strong = [{"skill_id": s,
               "confidence": actual.get(s, {}).get("confidence"),
               "evidence_ref": None}
              for s in result["strong_skills"]]
    weak = []
    for s in result["weak_skills"]:
        rec = actual.get(s, {})
        req = reqs.get(s, {})
        satisfied = rec.get("level", 0) >= req.get("required_level", 99)
        weak.append({"skill_id": s,
                     "confidence": rec.get("confidence"),
                     "note": "证据强度低" if satisfied else "等级未达标"})
    missing = [{"skill_id": s,
                "required_importance": reqs[s]["importance"],
                "jd_evidence_ref": _jd_line_ref(
                    jd_text, reqs[s].get("evidence_text", ""))}
               for s in result["missing_skills"]]
    return {
        "overall_score": result["overall_score"],
        "scoring_version": result["scoring_version"],
        "breakdown": result["breakdown"],
        "strong_skills": strong,
        "weak_skills": weak,
        "missing_skills": missing,
        "explanation": result["explanation"],
    }


def _jd_line_ref(jd_text: str, evidence_text: str) -> str:
    """证据在 JD 原文的 1-based 行号（规范化比较，尽力而为——D2 同源）。"""
    if not jd_text or not evidence_text:
        return "jd#L?"
    target = canonicalize_for_hash(evidence_text)
    for i, line in enumerate(jd_text.splitlines(), start=1):
        if target in canonicalize_for_hash(line):
            return f"jd#L{i}"
    return "jd#L?"


@router.get("/api/candidates/{candidate_id}/gaps")
def gaps(candidate_id: int,
         job_id: int | None = None,
         category: str | None = Query(None, pattern="^(?:" +
                                      "|".join(sorted(JOB_CATEGORIES)) + ")$"),
         market: str = Query("china", pattern="^(china|global)$"),
         min_freq: float = Query(0.20, gt=0, le=1),
         conn=Depends(get_conn)):
    """§2.9 缺口量化：job_id（单岗）/ category（市场聚合）二选一。"""
    try:
        return get_gaps(conn, candidate_id, job_id=job_id, category=category,
                        market=market, min_freq=min_freq)
    except GapQueryError as e:
        raise ApiError(422, "VALIDATION_ERROR", str(e)) from e
    except (GapCandidateNotFound, GapJobNotFound) as e:
        raise ApiError(404, "NOT_FOUND", str(e)) from e
