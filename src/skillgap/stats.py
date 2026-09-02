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


def create_snapshot(conn: psycopg.Connection, market: str, **slices) -> dict:
    """生成并持久化 market_snapshot（DATA_MODEL §2.10）。

    N < min_sample → 不写表（S11 失败处理：不生成 snapshot，返回样本不足）。
    快照 append-only：每次生成为新行，历史可追溯（computed_at 区分）。
    """
    result = skill_frequency(conn, market, **slices)
    if result["status"] != "ok":
        return {"market": market, "status": "insufficient_sample",
                "sample_size": result["sample_size"]}

    scope: dict[str, Any] = {"market": market}
    if slices.get("category"):
        scope["job_category"] = slices["category"]
    if slices.get("city"):
        scope["city"] = slices["city"]
    if slices.get("salary_min") is not None or slices.get("salary_max") is not None:
        scope["salary_band"] = [slices.get("salary_min"),
                                slices.get("salary_max")]
    if slices.get("window_start") and slices.get("window_end"):
        scope["window"] = [slices["window_start"], slices["window_end"]]

    import json
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO market_snapshot
               (scope, sample_size, skill_frequency, source_distribution,
                confidence, data_window_start, data_window_end, method_version)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (json.dumps(scope, ensure_ascii=False), result["sample_size"],
             json.dumps(result["skills"], ensure_ascii=False),
             json.dumps(result["source_distribution"], ensure_ascii=False),
             result["confidence"], result["window"]["start"],
             result["window"]["end"], METHOD_VERSION))
        sid = cur.fetchone()["id"]
    conn.commit()
    return {**result, "snapshot_id": sid, "evidence_ref": f"snapshot#{sid}"}


def skill_evidence(conn: psycopg.Connection, market: str, canonical_name: str,
                   **slices) -> dict:
    """技能 → 支撑 JD 列表（API §2.12 溯源底账）。

    同一 STATS_FILTER 口径（未授权贡献永不进底账）；底账不做样本量守门
    （它不是统计，是逐条列表），但口径与统计完全一致。
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM skill WHERE canonical_name = %s",
                    (canonical_name,))
        row = cur.fetchone()
        if row is None:
            return {"skill_id": canonical_name, "status": "unknown_skill",
                    "jd_refs": []}
        skill_id = row["id"]

    parts, params = _slice_where(**slices)
    where = f" AND {' AND '.join(parts)}" if parts else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT j.id AS job_id, j.title, j.source_type,
                       js.evidence_text, j.source_url, j.collected_at
                FROM job_skill js
                JOIN job j ON j.id = js.job_id
                WHERE js.skill_id = %s AND j.market = %s
                  AND {STATS_FILTER}{where}
                ORDER BY j.collected_at DESC, j.id""",
            (skill_id, market, *params))
        refs = [dict(r) for r in cur.fetchall()]
    return {"skill_id": canonical_name, "jd_count": len(refs), "jd_refs": refs}


# MARKET_RESEARCH.md §2.1 参考表（23 JD 小样本，[5] 来源）。
# 用途限定：方向一致性对照（假设检验），不作为真值——本模块的使命就是
# 用自建数据集把这张表变成可复现、可追溯的数据。
REFERENCE: dict[str, float] = {
    "Python": 1.00, "LLM 应用经验": 0.70, "LangChain": 0.80, "RAG": 0.60,
    "Prompt Engineering": 0.45, "向量数据库": 0.40, "Dify": 0.35,
    "微调/LoRA": 0.35, "LangGraph": 0.25, "FastAPI": 0.20, "AutoGen": 0.15,
    "Java": 0.15, "MCP": 0.10, "多模态理解": 0.10,
}

# 参考名 → 词表 canonical_name（taxonomy v1.4 已核对全部存在）。
# 向量数据库无单一对应技能 → 取 Milvus/Chroma/Qdrant 频率最大值。
REFERENCE_TO_CANONICAL: dict[str, list[str]] = {
    "Python": ["Python"], "LLM 应用经验": ["LLM 应用开发"],
    "LangChain": ["LangChain"], "RAG": ["RAG"],
    "Prompt Engineering": ["Prompt Engineering"],
    "向量数据库": ["Milvus", "Chroma", "Qdrant"],
    "Dify": ["Dify"], "微调/LoRA": ["SFT/LoRA"], "LangGraph": ["LangGraph"],
    "FastAPI": ["FastAPI"], "AutoGen": ["AutoGen"], "Java": ["Java"],
    "MCP": ["MCP"], "多模态理解": ["多模态"],
}


def kendall_tau(pairs: list[tuple[float, float]]) -> float:
    """Kendall tau-a（并列对不计入分子，分母为全部对数）。纯函数，零 LLM。"""
    n = len(pairs)
    if n < 2:
        return 0.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx = pairs[i][0] - pairs[j][0]
            dy = pairs[i][1] - pairs[j][1]
            if dx * dy > 0:
                concordant += 1
            elif dx * dy < 0:
                discordant += 1
    denom = n * (n - 1) / 2
    return round((concordant - discordant) / denom, 4)


def crosscheck_baseline(conn: psycopg.Connection, market: str,
                        **slices) -> dict:
    """自有数据集频率 vs MARKET_RESEARCH §2.1 参考表的方向一致性报告。

    ROADMAP Phase 4 验收项：方向一致性检查，差异写入报告（逐技能 diff）。
    """
    freq = skill_frequency(conn, market, **slices)
    if freq["status"] != "ok":
        return {"market": market, "status": "insufficient_sample",
                "sample_size": freq["sample_size"]}
    ours = {s["canonical_name"]: s["frequency"] for s in freq["skills"]}

    rows, pairs = [], []
    for ref_name, ref_freq in REFERENCE.items():
        canon = REFERENCE_TO_CANONICAL.get(ref_name, [])
        if not canon:
            rows.append({"reference_skill": ref_name, "status": "unmapped"})
            continue
        our_freq = max(ours.get(c, 0.0) for c in canon)
        rows.append({
            "reference_skill": ref_name, "canonical": canon,
            "reference_frequency": ref_freq, "our_frequency": our_freq,
            "diff": round(our_freq - ref_freq, 4),
        })
        pairs.append((ref_freq, our_freq))
    return {
        "market": market, "status": "ok",
        "sample_size": freq["sample_size"],
        "method": "kendall_tau_a", "tau": kendall_tau(pairs),
        "reference_source": "MARKET_RESEARCH.md §2.1（23 JD 小样本，非官方）",
        "note": "方向对照仅用于假设检验，不作为真值；差异逐条见 comparison",
        "comparison": rows,
        "method_version": METHOD_VERSION,
    }
