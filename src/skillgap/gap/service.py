"""Skill Gap 服务层（Phase 6，API §2.9）。

口径（docs/plans/2026-09-03-phase6-skill-gap.md D1-D8，DECISION_LOG C1/C2）：
- gap = 纯星级差（clamp ≥0），confidence 不进 gap（conf_factor 属 Phase 7）
- genuine/transferable 判定：§4.4 冻结规则，证据线 0.5
- 类目聚合：频次 ≥ min_freq(0.20) 入清单，required 取 must_have 映射最大值
- 排序：gap 降序、同 gap 按 frequency 降序；demand/cost 为 ROI 排序原料
  （Demand×Gap÷Cost 公式属 Phase 8 roi-v1，本层不计算分值）
- 零 LLM：纯 SQL + gapcalc 纯函数
"""
from __future__ import annotations

from typing import Any

import psycopg

from skillgap.gap.gapcalc import (
    EVIDENCE_THRESHOLD, GAP_METHOD_VERSION, classify, gap, required_level,
)
from skillgap.stats import STATS_FILTER


class CandidateNotFound(LookupError):
    """candidate_id 不存在。"""


class JobNotFound(LookupError):
    """job_id 不存在。"""


class GapQueryError(ValueError):
    """查询参数不合法（job_id 与 category 必须二选一）。"""


def get_gaps(conn: psycopg.Connection, candidate_id: int, *,
             job_id: int | None = None, category: str | None = None,
             market: str = "china", min_freq: float = 0.20) -> dict:
    """岗位要求 vs 画像的差距量化（API §2.9）。

    job_id（单岗）与 category（市场聚合）二选一；类目模式按 market 过滤。
    """
    if (job_id is None) == (category is None):
        raise GapQueryError("job_id 与 category 必须二选一")
    _require_candidate(conn, candidate_id)

    if job_id is not None:
        requirements = _requirements_for_job(conn, job_id)
        frequency = _market_frequency(conn, market)
        meta: dict[str, Any] = {"mode": "job", "job_id": job_id,
                                "market": market}
    else:
        requirements, frequency, n_cat = _requirements_for_category(
            conn, category, market, min_freq)
        meta = {"mode": "category", "category": category, "market": market,
                "category_sample_size": n_cat,
                "snapshot": _latest_snapshot(conn, market)}

    candidate = _candidate_skills(conn, candidate_id)

    gap_rows: list[dict] = []
    for r in requirements:
        actual = candidate.get(r["name"], {}).get("level", 0)
        g = gap(r["required"], actual)
        if g <= 0:
            continue
        freq = frequency.get(r["name"], 0.0)
        gap_rows.append({
            "skill_id": r["name"], "required_level": r["required"],
            "actual_level": actual, "gap": g,
            "demand": {"frequency": freq,
                       "sample_size": frequency.get("__n__", 0)},
            "cost": r["cost"], "_confidence":
                candidate.get(r["name"], {}).get("confidence", 0.0),
        })

    related, notes = _related_map(conn, [g["skill_id"] for g in gap_rows])
    evidence = {name: d["confidence"] for name, d in candidate.items()}
    types = classify(evidence, related, [g["skill_id"] for g in gap_rows])

    transferable = []
    for g in gap_rows:
        g["type"] = types[g["skill_id"]]
        if g["type"] == "transferable":
            via = _first_evidence_skill(g["skill_id"], related, evidence)
            g["via"] = via
            if via == g["skill_id"]:
                note = "自身已有证据但等级不足（需深化）"
            else:
                note = notes.get(
                    (g["skill_id"], via), f"关联技能 {via} 有可迁移证据")
            transferable.append({
                "skill_id": g["skill_id"], "via": via, "note": note,
            })

    gap_rows.sort(key=lambda g: (-g["gap"],
                                 -g["demand"]["frequency"],
                                 g["skill_id"]))
    for g in gap_rows:
        g.pop("_confidence")
    out = {"candidate_id": candidate_id, **meta,
           "gaps": gap_rows, "transferable": transferable,
           "gap_version": GAP_METHOD_VERSION}
    return out


# ---- 单岗要求 ----

def _requirements_for_job(conn, job_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM job WHERE id = %s", (job_id,))
        if cur.fetchone() is None:
            raise JobNotFound(f"job {job_id} 不存在")
        cur.execute(
            """SELECT s.canonical_name AS name, js.importance, js.intensity,
                      s.learning_cost AS cost
               FROM job_skill js JOIN skill s ON s.id = js.skill_id
               WHERE js.job_id = %s ORDER BY js.id""",
            (job_id,))
        rows = cur.fetchall()
    return [{"name": r["name"], "required": required_level(
                 r["importance"], r["intensity"]), "cost": r["cost"]}
            for r in rows]


# ---- 画像侧 ----

def _candidate_skills(conn, candidate_id: int) -> dict[str, dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.canonical_name AS name, cs.level, cs.confidence
               FROM candidate_skill cs JOIN skill s ON s.id = cs.skill_id
               WHERE cs.candidate_id = %s""",
            (candidate_id,))
        return {r["name"]: {"level": r["level"],
                            "confidence": float(r["confidence"])}
                for r in cur.fetchall()}


def _require_candidate(conn, candidate_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM candidate WHERE id = %s", (candidate_id,))
        if cur.fetchone() is None:
            raise CandidateNotFound(f"candidate {candidate_id} 不存在")


# ---- 相关技能集（§4.4：自身 + parent 一层 + transferable_to 双向） ----

def _related_map(conn, names: list[str]
                 ) -> tuple[dict[str, set[str]], dict[tuple[str, str], str]]:
    related: dict[str, set[str]] = {n: {n} for n in names}
    notes: dict[tuple[str, str], str] = {}
    if not names:
        return related, notes
    with conn.cursor() as cur:
        cur.execute(
            """SELECT s.canonical_name AS name, p.canonical_name AS parent
               FROM skill s LEFT JOIN skill p ON s.parent_skill_id = p.id
               WHERE s.canonical_name = ANY(%s)""",
            (names,))
        for r in cur.fetchall():
            if r["parent"]:
                related[r["name"]].add(r["parent"])
                notes[(r["name"], r["parent"])] = \
                    f"具备上级技能 {r['parent']} 的证据"
        cur.execute(
            """SELECT a.canonical_name AS a, b.canonical_name AS b, r.note
               FROM skill_relation r
               JOIN skill a ON a.id = r.skill_id
               JOIN skill b ON b.id = r.related_skill_id
               WHERE r.relation_type = 'transferable_to'
                 AND (a.canonical_name = ANY(%s) OR b.canonical_name = ANY(%s))""",
            (names, names))
        for r in cur.fetchall():
            related.setdefault(r["a"], {r["a"]}).add(r["b"])
            related.setdefault(r["b"], {r["b"]}).add(r["a"])
            note = r["note"] or f"{r['a']} 与 {r['b']} 能力可迁移"
            notes[(r["a"], r["b"])] = note
            notes[(r["b"], r["a"])] = note
    return related, notes


def _first_evidence_skill(skill: str, related: dict[str, set[str]],
                          evidence: dict[str, float]) -> str:
    """transferable 证据技能：自身优先（自身有证据=等级不足需深化），否则按名排序。"""
    others = sorted(t for t in related.get(skill, {skill})
                    if t != skill and evidence.get(t, 0.0) >= EVIDENCE_THRESHOLD)
    if evidence.get(skill, 0.0) >= EVIDENCE_THRESHOLD:
        return skill
    return others[0] if others else skill


# ---- demand 原料（stats S11 同口径的轻量查询） ----

def _market_frequency(conn, market: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT count(*) AS n FROM job j
                WHERE j.market = %s AND {STATS_FILTER}""",
            (market,))
        n = cur.fetchone()["n"]
        cur.execute(
            f"""SELECT s.canonical_name AS name,
                       round(count(DISTINCT js.job_id)::numeric
                             / NULLIF(%s, 0), 4) AS freq
                FROM job_skill js
                JOIN skill s ON s.id = js.skill_id
                JOIN job j ON j.id = js.job_id
                WHERE j.market = %s AND {STATS_FILTER}
                GROUP BY s.canonical_name""",
            (n, market))
        freq = {r["name"]: float(r["freq"] or 0.0) for r in cur.fetchall()}
    freq["__n__"] = n
    return freq


# ---- 类目聚合（D4：频次 ≥ min_freq 入清单；required 取 must_have 映射最大值） ----

def _requirements_for_category(conn, category: str, market: str,
                                min_freq: float
                                ) -> tuple[list[dict], dict, int]:
    """类目市场聚合要求 + 类目内频率（demand 口径）。

    返回 (requirements, frequency, n)。required_level 映射复用 gapcalc
    （单一事实来源）；无 must_have 行 → 2（nice 封顶档）。
    """
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT count(DISTINCT j.id) AS n FROM job j
                WHERE j.market = %s AND j.job_category = %s
                  AND {STATS_FILTER}""",
            (market, category))
        n = cur.fetchone()["n"]
        rows: list[Any] = []
        if n:
            cur.execute(
                f"""SELECT s.canonical_name AS name, js.importance,
                           js.intensity, s.learning_cost AS cost
                    FROM job_skill js
                    JOIN skill s ON s.id = js.skill_id
                    JOIN job j ON j.id = js.job_id
                    WHERE j.market = %s AND j.job_category = %s
                      AND {STATS_FILTER}""",
                (market, category))
            rows = cur.fetchall()

    grouped: dict[str, dict] = {}
    for r in rows:
        g = grouped.setdefault(r["name"], {"count": 0, "must": [], "cost":
                                           r["cost"]})
        g["count"] += 1
        if r["importance"] == "must_have":
            g["must"].append(required_level("must_have", r["intensity"]))

    requirements, frequency = [], {}
    for name, g in grouped.items():
        freq = round(g["count"] / n, 4)
        frequency[name] = freq
        if freq < min_freq:
            continue
        requirements.append({
            "name": name,
            "required": max(g["must"]) if g["must"] else 2,
            "cost": g["cost"],
        })
    frequency["__n__"] = n
    return requirements, frequency, n


def _latest_snapshot(conn, market: str) -> dict | None:
    """demand 溯源引用：该市场最新快照（无则 None）。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, sample_size, confidence, method_version,
                      computed_at
               FROM market_snapshot WHERE scope->>'market' = %s
               ORDER BY id DESC LIMIT 1""",
            (market,))
        row = cur.fetchone()
    if row is None:
        return None
    return {"id": row["id"], "sample_size": row["sample_size"],
            "confidence": row["confidence"],
            "method_version": row["method_version"],
            "computed_at": str(row["computed_at"])}
