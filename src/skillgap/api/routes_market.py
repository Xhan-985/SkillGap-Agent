"""市场端点（API.md §2.11 market/skills + §2.12 evidence——纯 SQL 零 LLM）。

D3 纪律：service 超集输出 → 契约形状裁剪（canonical_name→skill_id、
source_distribution 聚合为 tier 键、超集字段剥离）；
D10：evidence_ref = 溯源端点 URI（已 percent-encode，前端可直接点击）。
"""
from __future__ import annotations

from enum import Enum
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query

from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError
from skillgap.ingest.normalize import JOB_CATEGORIES
from skillgap.stats import skill_evidence, skill_frequency

# job_category 严格枚举（对齐 CLI choices；非法值 → 422 VALIDATION_ERROR）
JobCategory = Enum(
    "JobCategory", {c: c for c in sorted(JOB_CATEGORIES)}, type=str)

router = APIRouter(prefix="/api/market", tags=["market"])


def _slices(category: JobCategory | None, city: str | None,
            window_start: str | None, window_end: str | None) -> dict:
    """公共校验 + 组装切片 kwargs（窗口须成对提供——边界校验，边界即拒绝）。"""
    if (window_start is None) != (window_end is None):
        raise ApiError(422, "VALIDATION_ERROR", "window_start 与 window_end 必须成对提供")
    return {
        "category": category.value if category else None,
        "city": city,
        "window_start": window_start,
        "window_end": window_end,
    }


@router.get("/skills")
def market_skills(
    market: str = Query("china", pattern="^(china|global)$"),
    category: JobCategory | None = None,
    city: str | None = None,
    window_start: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    window_end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    min_sample: int = Query(30, ge=1),
    conn=Depends(get_conn),
):
    """§2.11 技能频率统计。N<min_sample → 200 + insufficient:true（冻结口径：
    这是正确行为而非故障，前端不当错误处理）。"""
    kwargs = _slices(category, city, window_start, window_end)
    out = skill_frequency(conn, market, min_sample=min_sample, **kwargs)
    if out["status"] != "ok":
        return {"market": market, "sample_size": out["sample_size"],
                "insufficient": True, "skills": []}

    dist: dict[str, float] = {}
    for row in out["source_distribution"]:
        dist[row["trust_tier"]] = round(
            dist.get(row["trust_tier"], 0.0) + row["share"], 4)
    return {
        "market": market,
        "window": out["window"],
        "sample_size": out["sample_size"],
        "confidence": out["confidence"],
        "source_distribution": dist,
        "skills": [
            {
                "skill_id": s["canonical_name"],
                "frequency": s["frequency"],
                "jd_count": s["jd_count"],
                "evidence_ref": "/api/market/skills/"
                                f"{quote(s['canonical_name'], safe='')}/evidence",
            }
            for s in out["skills"]
        ],
    }


@router.get("/skills/{skill_id}/evidence")
def market_skill_evidence(
    skill_id: str,
    market: str = Query("china", pattern="^(china|global)$"),
    conn=Depends(get_conn),
):
    """§2.12 频率溯源底账——每个百分比的逐条 JD 证据（同 STATS_FILTER 口径）。"""
    out = skill_evidence(conn, market, skill_id)
    if out.get("status") == "unknown_skill":
        raise ApiError(404, "NOT_FOUND", f"未知技能：{skill_id}")
    return {"skill_id": skill_id, "jd_refs": out["jd_refs"]}
