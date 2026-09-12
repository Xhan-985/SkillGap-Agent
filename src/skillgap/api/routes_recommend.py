"""推荐端点（API.md §2.10 POST /api/recommendations，M9）。

零模型调用（D6 红线）。错误映射（D2 双口径对照）：
- §2.10 契约 Error: SAMPLE_INSUFFICIENT——市场 N<30 拒推（ADR-008
  守门：无 fabricat 义）。服务层抛 RecommendError（消息前缀
  INSUFFICIENT_MARKET_DATA）→ 422 统一错误体。
  与 §2.11 market/skills 的 200+insufficient:true 形成"同一守门规则、
  两种表达"——展示层灰态可显示、决策层拒推（Phase 8 冻结语义）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError
from skillgap.recommend.service import (
    RECOMMEND_INSUFFICIENT_DATA, CandidateNotFound, RecommendError, recommend,
)

router = APIRouter(tags=["recommend"])


class RecommendRequest(BaseModel):
    candidate_id: int
    time_budget_days: int = Field(default=14)
    market: str = "china"


@router.post("/api/recommendations")
def recommendations(body: RecommendRequest, conn=Depends(get_conn)):
    """(画像, 预算, 市场) → ROI 优先级建议 + 项目模板。"""
    if body.time_budget_days not in (7, 14, 30):
        raise ApiError(422, "VALIDATION_ERROR",
                       "time_budget_days 必须为 7/14/30")
    if body.market not in ("china", "global"):
        raise ApiError(422, "VALIDATION_ERROR",
                       "market 仅允许 china|global")
    try:
        out = recommend(conn, body.candidate_id,
                        time_budget_days=body.time_budget_days,
                        market=body.market)
    except CandidateNotFound as e:
        raise ApiError(404, "NOT_FOUND", str(e)) from e
    except RecommendError as e:
        if RECOMMEND_INSUFFICIENT_DATA in str(e):
            # N<30 拒推（ADR-008）：决策端点错误体（D2 双口径之决策侧）
            raise ApiError(422, "SAMPLE_INSUFFICIENT",
                           str(e).split(": ", 1)[1]) from e
        raise ApiError(422, "VALIDATION_ERROR", str(e)) from e
    return out
