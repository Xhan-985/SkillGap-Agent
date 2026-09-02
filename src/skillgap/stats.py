"""S11 频率统计（Phase 4：切片 + 快照 + 溯源 + 交叉对照）。

口径（冻结，不得改动——DATA_MODEL §3 / DATA_PIPELINE S11 / docs/STATS_METHOD.md）：
  status='active' AND (source_type <> 'user_submitted' OR consent_status='market_analysis')
切片语义（变更须升 METHOD_VERSION 并先改 docs/STATS_METHOD.md）：
  category  精确匹配 job_category 枚举
  city      ILIKE 子串（"杭州，北京"多城格式）
  salary    区间重叠（salary_max >= min AND salary_min <= max）；NULL 薪资排除
  window    collected_at::date BETWEEN start AND end（含端点）
守门（ADR-008）：N < min_sample(默认 30) 不出统计；置信度 high>=200 / medium 50-200 / low 30-50。
本模块零 LLM 依赖（CI 静态检查目标之一，tests/test_stats.py 守卫测试锁定）。
"""
from __future__ import annotations

from typing import Any

import psycopg

STATS_FILTER = (
    "j.status = 'active' AND (j.source_type <> 'user_submitted' "
    "OR j.consent_status = 'market_analysis')"
)

METHOD_VERSION = "s11-v1"   # 口径版本：过滤 + 切片语义 + frequency 公式 + 舍入


def _slice_where(category=None, city=None, salary_min=None, salary_max=None,
                 window_start=None, window_end=None) -> tuple[list[str], list[Any]]:
    """切片 → 追加 WHERE 片段与参数（语义见模块 docstring 口径表）。"""
    parts: list[str] = []
    params: list[Any] = []
    if category:
        parts.append("j.job_category = %s")
        params.append(category)
    if city:
        parts.append("j.city ILIKE %s")
        params.append(f"%{city}%")
    if salary_min is not None or salary_max is not None:
        lo = salary_min if salary_min is not None else 0
        hi = salary_max if salary_max is not None else 10**9
        parts.append("j.salary_max >= %s AND j.salary_min <= %s")
        params.extend([lo, hi])
    if window_start and window_end:
        parts.append("j.collected_at::date BETWEEN %s::date AND %s::date")
        params.extend([window_start, window_end])
    return parts, params


def sample_size(conn: psycopg.Connection, market: str, **slices) -> int:
    parts, params = _slice_where(**slices)
    where = f" AND {' AND '.join(parts)}" if parts else ""
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) AS c FROM job j WHERE j.market = %s "
            f"AND {STATS_FILTER}{where}", (market, *params))
        return cur.fetchone()["c"]


def _confidence(n: int) -> str:
    if n >= 200:
        return "high"
    if n >= 50:
        return "medium"
    return "low"


def skill_frequency(conn: psycopg.Connection, market: str, *, category=None,
                    city=None, salary_min=None, salary_max=None,
                    window_start=None, window_end=None,
                    min_sample: int = 30) -> dict:
    """频率统计（API §2.11 服务层结构）：切片 + 样本量守门 + 置信度分级。"""
    slices = dict(category=category, city=city, salary_min=salary_min,
                  salary_max=salary_max, window_start=window_start,
                  window_end=window_end)
    n = sample_size(conn, market, **slices)
    if n < min_sample:
        return {"market": market, "sample_size": n,
                "status": "insufficient_sample"}

    parts, params = _slice_where(**slices)
    where = f" AND {' AND '.join(parts)}" if parts else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT s.canonical_name, count(DISTINCT js.job_id) AS jd_count
                FROM job_skill js
                JOIN job j ON j.id = js.job_id
                JOIN skill s ON s.id = js.skill_id
                WHERE j.market = %s AND {STATS_FILTER}{where}
                GROUP BY s.canonical_name
                ORDER BY jd_count DESC, s.canonical_name""",
            (market, *params))
        rows = cur.fetchall()
        cur.execute(
            f"""SELECT ds.source_name, ds.trust_tier, count(*) AS c
                FROM job j JOIN data_source ds ON ds.id = j.source_id
                WHERE j.market = %s AND {STATS_FILTER}{where}
                GROUP BY ds.source_name, ds.trust_tier ORDER BY c DESC""",
            (market, *params))
        dist = cur.fetchall()
        cur.execute(
            f"""SELECT min(j.collected_at::date) AS lo, max(j.collected_at::date) AS hi
                FROM job j WHERE j.market = %s AND {STATS_FILTER}{where}""",
            (market, *params))
        win = cur.fetchone()

    skills = [
        {"canonical_name": r["canonical_name"], "jd_count": r["jd_count"],
         "frequency": round(r["jd_count"] / n, 4)}
        for r in rows
    ]
    source_distribution = [
        {"source_name": r["source_name"], "trust_tier": r["trust_tier"],
         "count": r["c"], "share": round(r["c"] / n, 4)}
        for r in dist
    ]
    filters = {k: v for k, v in slices.items() if v is not None}
    return {
        "market": market, "sample_size": n, "status": "ok",
        "confidence": _confidence(n),
        "window": {"start": str(win["lo"]) if win["lo"] else None,
                   "end": str(win["hi"]) if win["hi"] else None},
        "filters": filters,
        "skills": skills, "source_distribution": source_distribution,
        "stats_filter": STATS_FILTER, "method_version": METHOD_VERSION,
    }
