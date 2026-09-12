"""页面路由（SSR，Phase 10 D8）——/ Dashboard 六视图（M10）。

数据组装全只读（GET 页面零写副作用）：
- 市场热门技能：skill_frequency（stats service）
- 我的画像 / 技能雷达：get_profile + get_gaps（类目聚合，gap-v1）
- 我的缺口 + 推荐行动：最近一条 recommendation（SELECT，非重算——
  recommend() 有落库副作用，页面不调）
- 匹配概览：C6 冻结——前端 localStorage 缓存最近一次 /api/match
  响应（T7 app.js 填充），SSR 仅渲染容器与空态

页面路由不进 OpenAPI schema（API 契约仅 /api/*，API.md §0）。
雷达 SVG 为展示组装（D6 手写）：坐标由 level 0-5 线性映射，业务
数字全部来自 service 输出，无前端计算新数字。
"""
from __future__ import annotations

import math
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from skillgap.api.deps import get_conn
from skillgap.gap.service import get_gaps
from skillgap.ingest.normalize import JOB_CATEGORIES
from skillgap.profile.service import CandidateNotFound, get_profile
from skillgap.stats import skill_frequency

templates = Jinja2Templates(
    directory=str(Path(__file__).parent / "templates"))

router = APIRouter(include_in_schema=False)

RADAR_CATEGORY = "ai_application_dev"   # 默认类目（可切换——UI_SPEC §2.1）

_CONF_LABEL = {"high": "高", "medium": "中", "low": "低"}


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request,
              candidate_id: int | None = None,
              market: str = Query("china", pattern="^(china|global)$"),
              category: str = Query(
                  RADAR_CATEGORY,
                  pattern="^(?:" + "|".join(JOB_CATEGORIES) + ")$"),
              conn=Depends(get_conn)):
    """六视图总览（UI_SPEC §2.1）。candidate_id 经 query（localStorage
    由前端 JS 附加——C6；SSR 直链可分享）；category 驱动雷达目标类目。"""
    freq = skill_frequency(conn, market)
    market_view = _market_view(freq, market)

    profile = None
    candidate_missing = False
    gaps = None
    if candidate_id is not None:
        try:
            profile = get_profile(conn, candidate_id)
        except CandidateNotFound:
            candidate_missing = True
        if profile is not None:
            gaps = get_gaps(conn, candidate_id, category=category,
                            market=market)
    last_rec = (_last_recommendation(conn, candidate_id)
               if profile is not None else None)
    radar = _radar_series(profile, gaps, category)

    return templates.TemplateResponse(request, "dashboard.html", {
        "request": request, "market": market,
        "market_view": market_view, "candidate_id": candidate_id,
        "profile": profile, "gaps": gaps, "last_rec": last_rec,
        "radar": radar, "candidate_missing": candidate_missing,
    })


def _page(name: str, request: Request, **ctx):
    """流程页共用：market 常驻 + candidate_id（localStorage 由 JS 附加，
    SSR 直链可分享）。"""
    return templates.TemplateResponse(request, f"{name}.html", ctx)


@router.get("/resume", response_class=HTMLResponse)
def resume_page(request: Request):
    return _page("resume", request, market="china", candidate_id=None)


@router.get("/jd", response_class=HTMLResponse)
def jd_page(request: Request):
    return _page("jd", request, market="china", candidate_id=None)


@router.get("/match", response_class=HTMLResponse)
def match_page(request: Request):
    return _page("match", request, market="china", candidate_id=None)


@router.get("/recommend", response_class=HTMLResponse)
def recommend_page(request: Request):
    return _page("recommend", request, market="china", candidate_id=None)


@router.get("/market", response_class=HTMLResponse)
def market_page(request: Request,
                market: str = Query("china", pattern="^(china|global)$"),
                conn=Depends(get_conn)):
    """市场页 SSR 直出频率表（数据窗口标注 + Adzuna 归属，UI_SPEC §2.6）。"""
    freq = skill_frequency(conn, market)
    view = _market_view(freq, market)
    return _page("market", request, market=market, candidate_id=None,
                 market_view=view)


def _market_view(freq: dict, market: str) -> dict:
    """skill_frequency 超集 → 模板形状（D5 灰态口径；D3 超集裁剪）。"""
    if freq.get("status") == "insufficient_sample":
        return {"market": market, "insufficient": True,
                "sample_size": freq["sample_size"], "skills": [],
                "window": None, "confidence": None,
                "source_distribution": None}
    return {"market": market, "insufficient": False,
            "sample_size": freq["sample_size"],
            "confidence": freq["confidence"],
            "confidence_label": _CONF_LABEL.get(freq["confidence"], "—"),
            "window": freq.get("window"),
            "source_distribution": freq.get("source_distribution"),
            "skills": freq.get("skills", [])}


def _last_recommendation(conn, candidate_id: int) -> dict | None:
    """最近一条推荐（只读；recommend() 本身有落库副作用，页面不重算）。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT priority_items, project_suggestions, time_budget_days
               FROM recommendation WHERE candidate_id = %s
               ORDER BY id DESC LIMIT 1""", (candidate_id,))
        row = cur.fetchone()
    if row is None:
        return None
    return {"priority_items": row["priority_items"],
            "project_suggestions": row["project_suggestions"],
            "time_budget_days": row["time_budget_days"]}


def _radar_series(profile: dict | None, gaps: dict | None, category: str,
                  max_axes: int = 8) -> dict | None:
    """画像 vs 类目要求 双多边形数据（D6 展示组装）。

    顶点 = 缺口技能 ∪ 画像技能（≤max_axes）；required 取 gaps 的
    required_level，纯画像技能（类目清单未要求）required=actual
    展示为已覆盖（展示层约定：类目聚合对其无更高要求，非计算新数字）。
    顶点 <3 时多边形退化 → enough=False 渲染占位文案。
    """
    if profile is None:
        return None
    actual: dict[str, dict] = {s["skill_id"]: s for s in profile["skills"]}
    required: dict[str, int] = {}
    if gaps:
        for g in gaps["gaps"]:
            required[g["skill_id"]] = g["required_level"]
            actual.setdefault(g["skill_id"], {"level": g["actual_level"]})
    names = list(dict.fromkeys(
        list(required) + [n for n in actual if n not in required]))[:max_axes]
    if len(names) < 3:
        return {"enough": False}

    axes = [{"skill": n,
             "actual": actual.get(n, {}).get("level", 0),
             "required": required.get(n, actual.get(n, {}).get("level", 0))}
            for n in names]

    cx, cy, radius, top = 130, 130, 100, 5

    def _pts(values: list[float]) -> str:
        coords = []
        for i, v in enumerate(values):
            ang = -math.pi / 2 + 2 * math.pi * i / len(values)
            r = radius * (v / top)
            coords.append(f"{cx + r * math.cos(ang):.1f},"
                          f"{cy + r * math.sin(ang):.1f}")
        return " ".join(coords)

    n = len(axes)
    rings = [_pts([lvl] * n) for lvl in range(1, top + 1)]
    labels = []
    for i, ax in enumerate(axes):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        labels.append({
            "skill": ax["skill"],
            "x": round(cx + (radius + 22) * math.cos(ang), 1),
            "y": round(cy + (radius + 22) * math.sin(ang) + 4, 1)})
    return {"enough": True, "axes": axes,
            "actual_points": _pts([a["actual"] for a in axes]),
            "required_points": _pts([a["required"] for a in axes]),
            "grid_rings": rings, "labels": labels,
            "category": category}
