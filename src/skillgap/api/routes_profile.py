"""画像端点（API.md §2.5 resumes/analyze + §2.6 profile GET + §2.7 DELETE）。

extractor 依赖注入（app 层装配真实 LLM；测试经 dependency_overrides 注 Fake）。
契约裁剪（D3）：§2.5 响应 = CLI 超集剥 notices；技能层超集键（source_type/
evidence_ref=null 的 GET 版差异）按契约保留必要字段。
错误映射（D2）：ExtractionFailed→502 LLM_EXTRACTION_FAILED；LLMError→502
LLM_TIMEOUT（provider 层不区分超时与其他网络错误——统一 LLM_TIMEOUT 是
契约对"上游不可用"的显式分类，details 携带原始异常名保真）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError
from skillgap.config import settings
from skillgap.profile.service import (
    CandidateNotFound, ResumeValidationError, analyze_resume, delete_candidate,
    get_profile,
)

router = APIRouter(tags=["profile"])


class ResumeAnalyzeRequest(BaseModel):
    resume_text: str
    candidate_id: int | None = None


def make_resume_extractor(conn=Depends(get_conn)):
    """真实 LLM 装配（复用 cli.py 同构逻辑；未配 key → 502 明示，不静默）。"""
    from skillgap.llm.gateway import LLMGateway
    from skillgap.llm.provider import OpenAICompatibleProvider
    from skillgap.profile.extractor import LLMResumeExtractor
    from skillgap.profile.prompt import RESUME_PROMPT_VERSION

    if not settings.llm_api_key:
        raise ApiError(502, "LLM_EXTRACTION_FAILED",
                       "服务端未配置 LLM_API_KEY，无法执行简历分析")
    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url, api_key=settings.llm_api_key,
        model=settings.llm_model, timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries)
    gateway = LLMGateway(conn, provider, RESUME_PROMPT_VERSION)
    return LLMResumeExtractor(gateway)


@router.post("/api/resumes/analyze")
def resumes_analyze(body: ResumeAnalyzeRequest,
                    conn=Depends(get_conn),
                    extractor=Depends(make_resume_extractor)):
    """§2.5 简历 → 证据化画像。部分失败策略：未识别技能不出现，不伪造。"""
    from skillgap.extract.llm_extractor import ExtractionFailed
    from skillgap.llm.provider import LLMError

    try:
        out = analyze_resume(conn, body.resume_text, extractor,
                             body.candidate_id)
    except ResumeValidationError as e:
        raise ApiError(422, "VALIDATION_ERROR", str(e)) from e
    except ExtractionFailed as e:
        raise ApiError(502, "LLM_EXTRACTION_FAILED",
                       str(e), {"retries": settings.llm_max_retries}) from e
    except LLMError as e:
        raise ApiError(502, "LLM_TIMEOUT", "LLM 上游调用失败",
                       {"cause": type(e).__name__}) from e
    except CandidateNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e)) from e
    # 契约裁剪：剥 notices（CLI 超集字段）
    return {"candidate_id": out["candidate_id"],
            "skills": out["skills"], "soft_profile": out["soft_profile"]}


@router.get("/api/candidates/{candidate_id}/profile")
def candidates_profile(candidate_id: int, conn=Depends(get_conn)):
    """§2.6 画像查询：evidence_ref=null（简历原文不落库，D2）。"""
    try:
        return get_profile(conn, candidate_id)
    except CandidateNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e)) from e


@router.delete("/api/candidates/{candidate_id}", status_code=204)
def candidates_delete(candidate_id: int, conn=Depends(get_conn)):
    """§2.7 级联删除画像/证据/匹配结果；不存在 → 404（不区分原因）。"""
    if not delete_candidate(conn, candidate_id):
        raise ApiError(404, "NOT_FOUND", f"candidate {candidate_id} 不存在")
