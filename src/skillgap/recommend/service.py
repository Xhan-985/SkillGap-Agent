"""Recommend 服务层（Phase 8，API §2.10）。

装配（C4 裁决：market 全类目聚合，复用 D-2026-09-03-13 规则）：
市场聚合 gap（频次 ≥0.20 入清单、required 取 must 映射最大值）+
snapshot demand + 项目模板匹配 → roi.compute_priority →
recommendation 落库。零模型调用（D6 红线）。

模板匹配（D4）：缺口技能 ∩ target_skills ≥1 → 候选；排序按交集
大小 → est_days 升序；过滤 est_days ≤ time_budget_days；source 必填。
"""
from __future__ import annotations

import json
from pathlib import Path

from psycopg.types.json import Json

from skillgap.gap.gapcalc import required_level as _required_level
from skillgap.recommend.roi import (
    MIN_FREQUENCY, ROI_VERSION, TOP_K, compute_priority, render_rationale,
)
from skillgap.stats import STATS_FILTER

DEFAULT_TEMPLATES_PATH = "data/project_templates.json"
RECOMMEND_INSUFFICIENT_DATA = "INSUFFICIENT_MARKET_DATA"


class CandidateNotFound(LookupError):
    """candidate_id 不存在。"""


class RecommendError(ValueError):
    """推荐前置数据不足或参数不合法。"""


def recommend(conn, candidate_id: int, time_budget_days: int = 14,
              market: str = "china", k: int = TOP_K,
              templates_path: str | None = None) -> dict:
    """(画像, 预算) → ROI 优先级建议（API §2.10 结构）+ 落库。"""
    if time_budget_days not in (7, 14, 30):
        raise RecommendError("time_budget_days 必须为 7/14/30")
    _require_candidate(conn, candidate_id)

    n = _market_job_count(conn, market)
    if n < 30:
        raise RecommendError(
            f"{RECOMMEND_INSUFFICIENT_DATA}: market={market} 仅 {n} 岗"
            "（<30，ADR-008 守门），不生成推荐")

    reqs = _market_requirements(conn, market)          # 频次过滤后清单
    candidate = _candidate_skills(conn, candidate_id)
    snapshot = _latest_snapshot(conn, market)

    gap_items = []
    for name, r in reqs.items():
        actual = candidate.get(name, {}).get("level", 0)
        g = r["required"] - actual
        if g <= 0:
            continue
        gap_items.append({
            "skill": name, "frequency": r["frequency"],
            "sample_size": n,
            "evidence_ref": {"snapshot_id": snapshot["id"],
                             "sample_size": snapshot["sample_size"],
                             "computed_at": snapshot["computed_at"]}
            if snapshot else None,
            "gap": g, "cost": r["cost"],
        })

    # genuine/transferable 复用 gap 层判定（§4.4：证据线 0.5）
    types = _classify_types(conn, candidate, [i["skill"] for i in gap_items])
    for it in gap_items:
        it["type"] = types.get(it["skill"], "genuine")

    priority = compute_priority(gap_items)[:k]
    for it in priority:
        it["rationale"] = render_rationale(it, time_budget_days)

    templates = _load_templates(templates_path or DEFAULT_TEMPLATES_PATH)
    gap_set = {i["skill"] for i in priority}
    suggestions = _match_templates(templates, gap_set, time_budget_days)

    out = {"candidate_id": candidate_id, "market": market,
           "time_budget_days": time_budget_days,
           "formula_version": ROI_VERSION,
           "priority_items": priority,
           "project_suggestions": suggestions,
           "snapshot_ref": ({"id": snapshot["id"],
                             "sample_size": snapshot["sample_size"]}
                            if snapshot else None)}
    if not priority:
        out["no_gaps"] = True
    _persist(conn, candidate_id, time_budget_days, out)
    return out


# ---- 市场聚合（C4：scope 从 category 扩为 market，规则同源） ----

def _market_job_count(conn, market: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT count(DISTINCT j.id) AS n FROM job j
                WHERE j.market = %s AND {STATS_FILTER}""",
            (market,))
        return cur.fetchone()["n"]


def _market_requirements(conn, market: str) -> dict[str, dict]:
    """频次 ≥0.20 入清单；required 取 must_have 映射最大值（无 must→2）。"""
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT s.canonical_name AS name, js.importance, js.intensity,
                       s.learning_cost AS cost
                FROM job_skill js
                JOIN skill s ON s.id = js.skill_id
                JOIN job j ON j.id = js.job_id
                WHERE j.market = %s AND {STATS_FILTER}""",
            (market,))
        rows = cur.fetchall()
        n_cur = conn.execute(
            f"SELECT count(DISTINCT j.id) AS n FROM job j "
            f"WHERE j.market = %s AND {STATS_FILTER}", (market,)
        ).fetchone()["n"]
    grouped: dict[str, dict] = {}
    for r in rows:
        g = grouped.setdefault(r["name"], {"count": 0, "must": [],
                                            "cost": r["cost"]})
        g["count"] += 1
        if r["importance"] == "must_have":
            g["must"].append(_required_level("must_have", r["intensity"]))
    reqs = {}
    for name, g in grouped.items():
        freq = round(g["count"] / n_cur, 4)
        if freq < MIN_FREQUENCY:
            continue
        reqs[name] = {"frequency": freq,
                      "required": max(g["must"]) if g["must"] else 2,
                      "cost": g["cost"]}
    return reqs


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


def _classify_types(conn, candidate: dict, names: list[str]) -> dict[str, str]:
    """genuine/transferable：有画像记录（conf ≥0.5）的缺口=transferable
    候选（自身证据需深化），否则 genuine（无任何证据）。"""
    return {n: ("transferable"
                if candidate.get(n, {}).get("confidence", 0.0) >= 0.5
                else "genuine") for n in names}


def _latest_snapshot(conn, market: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, sample_size, computed_at FROM market_snapshot
               WHERE scope->>'market' = %s ORDER BY id DESC LIMIT 1""",
            (market,))
        row = cur.fetchone()
    return ({"id": row["id"], "sample_size": row["sample_size"],
             "computed_at": str(row["computed_at"])} if row else None)


# ---- 模板匹配（D4） ----

def _load_templates(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _match_templates(templates: list[dict], gap_set: set[str],
                     budget: int) -> list[dict]:
    scored = []
    for t in templates:
        matched = sorted(set(t["target_skills"]) & gap_set)
        if not matched or t["est_days"] > budget:
            continue
        scored.append({
            "template_id": t["template_id"], "title": t["title"],
            "matched_skills": matched,
            "target_skills": t["target_skills"],
            "est_days": t["est_days"], "cost": t["cost"],
            "source": t["source"],
            "rationale": (f"覆盖缺口技能 {len(matched)} 项（"
                          f"{'、'.join(matched)}），预计 {t['est_days']} 天"
                          f"在 {budget} 天预算内可完成。"),
        })
    scored.sort(key=lambda s: (-len(s["matched_skills"]), s["est_days"],
                               s["template_id"]))
    return scored


# ---- 落库 ----

def _persist(conn, candidate_id: int, budget: int, out: dict) -> None:
    top_gain = (out["priority_items"][0]["potential_gain"]
                if out["priority_items"] else 0.0)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO recommendation
               (candidate_id, time_budget_days, priority_items,
                potential_gain, project_suggestions)
               VALUES (%s, %s, %s, %s, %s)""",
            (candidate_id, budget, Json(out["priority_items"]), top_gain,
             Json(out["project_suggestions"])))
    conn.commit()
