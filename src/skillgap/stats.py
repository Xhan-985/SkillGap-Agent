"""S11 频率统计空跑（Phase 2：口径冻结；完整 Market Intelligence 属 Phase 4）。

口径（冻结，不得改动——DATA_MODEL §3 / DATA_PIPELINE S11 / B1 修复）：
  status='active' AND (source_type <> 'user_submitted' OR consent_status='market_analysis')
守门（ADR-008）：N < 30 不出统计；置信度 high>=200 / medium 50-200 / low 30-50。
本模块零 LLM 依赖（CI 静态检查目标之一）。
"""
from __future__ import annotations

import psycopg

STATS_FILTER = (
    "j.status = 'active' AND (j.source_type <> 'user_submitted' "
    "OR j.consent_status = 'market_analysis')"
)


def sample_size(conn: psycopg.Connection, market: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) AS c FROM job j WHERE j.market = %s "
            f"AND {STATS_FILTER}", (market,))
        return cur.fetchone()["c"]


def _confidence(n: int) -> str:
    if n >= 200:
        return "high"
    if n >= 50:
        return "medium"
    return "low"


def skill_frequency(conn: psycopg.Connection, market: str) -> dict:
    """空跑口径：技能频率 + 样本量 + 来源分布 + 置信度（Phase 4 冻结为快照）。"""
    n = sample_size(conn, market)
    if n < 30:
        return {"market": market, "sample_size": n,
                "status": "insufficient_sample"}

    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT s.canonical_name, count(DISTINCT js.job_id) AS jd_count
                FROM job_skill js
                JOIN job j ON j.id = js.job_id
                JOIN skill s ON s.id = js.skill_id
                WHERE j.market = %s AND {STATS_FILTER}
                GROUP BY s.canonical_name
                ORDER BY jd_count DESC, s.canonical_name""",
            (market,))
        rows = cur.fetchall()
        cur.execute(
            f"""SELECT ds.source_name, ds.trust_tier, count(*) AS c
                FROM job j JOIN data_source ds ON ds.id = j.source_id
                WHERE j.market = %s AND {STATS_FILTER}
                GROUP BY ds.source_name, ds.trust_tier ORDER BY c DESC""",
            (market,))
        dist = cur.fetchall()

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
    return {
        "market": market, "sample_size": n, "status": "ok",
        "confidence": _confidence(n),
        "skills": skills, "source_distribution": source_distribution,
        "stats_filter": STATS_FILTER,
    }
