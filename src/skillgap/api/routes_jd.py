"""JD 分析端点（API.md §2.1 POST /api/jd/analyze，M1）。

无状态即时计算，默认不落库（B1：数据入库唯一通道 contribute + consent）。
三层分离（extraction 是唯一受控 LLM 节点）：LLM 只出 skills +
soft_requirements；market/language/job_category 确定性规则。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError
from skillgap.config import settings

router = APIRouter(tags=["jd"])


class JDAnalyzeRequest(BaseModel):
    jd_text: str
    title: str = ""


def make_jd_extractor(conn=Depends(get_conn)):
    """真实 LLM 装配（同 cli jd-analyze / routes_match 工厂同构）。"""
    from skillgap.extract.llm_extractor import LLMSkillExtractor
    from skillgap.extract.prompt import PROMPT_VERSION
    from skillgap.llm.gateway import LLMGateway
    from skillgap.llm.provider import OpenAICompatibleProvider

    if not settings.llm_api_key:
        raise ApiError(502, "LLM_EXTRACTION_FAILED",
                       "服务端未配置 LLM_API_KEY，无法分析 JD")
    provider = OpenAICompatibleProvider(
        base_url=settings.llm_base_url, api_key=settings.llm_api_key,
        model=settings.llm_model, timeout=settings.llm_timeout,
        max_retries=settings.llm_max_retries)
    gateway = LLMGateway(conn, provider, PROMPT_VERSION)
    return LLMSkillExtractor(gateway)


@router.post("/api/jd/analyze")
def jd_analyze(body: JDAnalyzeRequest,
               conn=Depends(get_conn),
               extractor=Depends(make_jd_extractor)):
    """无状态 JD 分析：不落库（测试锚定），extraction_meta 透传。"""
    from skillgap.extract.analyzer import JDValidationError, analyze_jd
    from skillgap.extract.llm_extractor import ExtractionFailed
    from skillgap.llm.provider import LLMError

    try:
        return analyze_jd(conn, body.jd_text, extractor, body.title)
    except JDValidationError as e:
        raise ApiError(422, "VALIDATION_ERROR", str(e)) from e
    except ExtractionFailed as e:
        raise ApiError(502, "LLM_EXTRACTION_FAILED",
                       str(e), {"retries": settings.llm_max_retries}) from e
    except LLMError as e:
        raise ApiError(502, "LLM_TIMEOUT", "LLM 上游调用失败",
                       {"cause": type(e).__name__}) from e
