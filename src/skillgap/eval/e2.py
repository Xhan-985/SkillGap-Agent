"""E2 评测器（岗位匹配质量回归——EVALUATION_PLAN §3）。

口径（预声明，跑分前冻结——§3.2/§3.3）：
- 指标：Spearman ρ（平均秩 + Pearson，手写无 scipy）、MAE、三组 Jaccard、
  micro P/R/F1（池化三组 (对,技能) 决策）+ **Missing 组单独主报** +
  macro F1（低频组不隐身）
- 阈值：pass/warn/block 同表——ρ ≥0.7/0.5、MAE ≤12/20、Jaccard ≥0.7/0.5、
  F1 ≥0.7/0.5；verdict 取各指标最差档
- 对抗三用例聚合：裸声明分差 ≥10 / 无关 JD 上界 ≤29 / 别名变体分数一致
- 红线：LLM 不参与指标计算（§1.2）；系统分由 match.scoring 纯函数产出
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

E2_THRESHOLDS = {
    "spearman": {"pass": 0.7, "warn": 0.5},
    "mae": {"pass": 12, "warn": 20},
    "jaccard": {"pass": 0.7, "warn": 0.5},
    "prf": {"pass": 0.7, "warn": 0.5},
}
GROUPS = ("strong", "weak", "missing")


# ---- 基础指标（纯函数） ----

def _average_ranks(values: Sequence[float]) -> list[float]:
    """并列取平均秩（Spearman 标准处理）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1            # 1-based 平均秩
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """秩相关（Pearson on 平均秩）。常数序列 / 空输入 → 0.0。"""
    n = len(x)
    if n < 2 or n != len(y):
        return 0.0
    rx, ry = _average_ranks(list(x)), _average_ranks(list(y))
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den_x = sum((a - mx) ** 2 for a in rx)
    den_y = sum((b - my) ** 2 for b in ry)
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y) ** 0.5


def mae(system: Sequence[float], human: Sequence[float]) -> float:
    return sum(abs(a - b) for a, b in zip(system, human)) / len(system)


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0        # 双空 = 完全一致
    return len(a & b) / len(a | b)


def prf(system_groups: Mapping[str, set],
        human_groups: Mapping[str, set],
        group: str | None = None) -> tuple[float, float, float]:
    """(precision, recall, f1)——group=None 池化三组，否则单组。

    双空 = 完全一致（与 jaccard 约定对齐）→ (1.0, 1.0, 1.0)。
    """
    keys = [group] if group else list(GROUPS)
    sys_items = {(k, s) for k in keys
                 for s in system_groups.get(k, set())}
    hum_items = {(k, s) for k in keys
                 for s in human_groups.get(k, set())}
    return _prf_from_sets(sys_items, hum_items)


def _prf_from_sets(sys_set: set, hum_set: set) -> tuple[float, float, float]:
    tp = len(sys_set & hum_set)
    if not sys_set and not hum_set:
        return 1.0, 1.0, 1.0
    p = tp / len(sys_set) if sys_set else 1.0
    r = tp / len(hum_set) if hum_set else 1.0
    f1 = 2 * p * r / (p + r) if tp else 0.0
    return p, r, f1


# ---- 汇总 + verdict ----

def _grade(value: float, table: Mapping[str, float],
           higher_better: bool = True) -> str:
    if higher_better:
        if value >= table["pass"]:
            return "pass"
        if value >= table["warn"]:
            return "warn"
        return "block"
    if value <= table["pass"]:
        return "pass"
    if value <= table["warn"]:
        return "warn"
    return "block"


def compute_metrics(pairs: Sequence[Mapping],
                    adversarial: Mapping | None = None) -> dict:
    """pairs: [{system_score, human_score, system_groups, human_groups}]。

    micro 池化 (对, 组, 技能) 三元组决策——不同对的同名技能各计一次
    （与 E1 的跨样本池化口径一致）；macro 逐组平均。
    adversarial（可选）：{"bare_claim_pair": (hi, lo), "unrelated_upper": U,
    "alias_pair": (a, b)}——对抗用例断言原料。
    """
    sys_scores = [p["system_score"] for p in pairs]
    hum_scores = [p["human_score"] for p in pairs]
    rho = spearman(sys_scores, hum_scores)
    mean_abs = mae(sys_scores, hum_scores)
    jac = sum(jaccard(p["system_groups"].get(g, set()),
                      p["human_groups"].get(g, set()))
              for p in pairs for g in GROUPS) / (len(pairs) * len(GROUPS))

    sys_items = {(i, g, s) for i, p in enumerate(pairs)
                 for g in GROUPS for s in p["system_groups"].get(g, set())}
    hum_items = {(i, g, s) for i, p in enumerate(pairs)
                 for g in GROUPS for s in p["human_groups"].get(g, set())}

    micro = _prf_from_sets(sys_items, hum_items)
    missing = _prf_from_sets({t for t in sys_items if t[1] == "missing"},
                             {t for t in hum_items if t[1] == "missing"})
    macro_f1 = sum(
        _prf_from_sets({t for t in sys_items if t[1] == g},
                       {t for t in hum_items if t[1] == g})[2]
        for g in GROUPS) / len(GROUPS)

    out = {
        "sample_size": len(pairs),
        "spearman": round(rho, 4),
        "mae": round(mean_abs, 2),
        "jaccard": round(jac, 4),
        "prf_micro": {"precision": round(micro[0], 4),
                      "recall": round(micro[1], 4),
                      "f1": round(micro[2], 4)},
        "prf_missing": {"precision": round(missing[0], 4),
                        "recall": round(missing[1], 4),
                        "f1": round(missing[2], 4)},
        "macro_f1": round(macro_f1, 4),
    }

    grades = [_grade(rho, E2_THRESHOLDS["spearman"]),
             _grade(mean_abs, E2_THRESHOLDS["mae"], higher_better=False),
             _grade(jac, E2_THRESHOLDS["jaccard"]),
             _grade(micro[2], E2_THRESHOLDS["prf"])]
    out["verdict"] = ("block" if "block" in grades else
                      "warn" if "warn" in grades else "pass")

    if adversarial:
        hi, lo = adversarial["bare_claim_pair"]
        out["adversarial"] = {
            "bare_claim_gap": round(hi - lo, 1),
            "bare_claim_ok": hi - lo >= 10,
            "unrelated_scores_max": adversarial.get(
                "unrelated_scores_max", 0.0),
            "unrelated_ok": adversarial.get("unrelated_scores_max",
                                            0.0) <= adversarial.get(
                                                "unrelated_upper", 29),
            "alias_scores_equal": bool(
                adversarial["alias_pair"][0] == adversarial["alias_pair"][1]),
        }
    return out


# ==================== 评测器（DB 装配层） ====================
# 与 e1.py 同模式：seed_eval2 入库（幂等）→ run_e2 物化 + 跑分 +
# eval_run 留痕。物化策略（计划 D9）：
# - 画像：candidate 以 soft_profile.e2_profile_id 标记 upsert（重复跑重建）
# - JD：jd_source "job#N" 直接用库内岗；其余（别名变体样本）插入为
#   active 零技能 job → backfill_pending 走 LLM 抽取（content_hash 幂等）

DATASET_VERSION = "e2-v1"
DATASET_PATH = "data/eval/e2_seed_v1.json"


def seed_eval2(conn, dataset_path: str = DATASET_PATH) -> int:
    """E2 标注集幂等入库（evaluation_sample eval_type='matching'）。"""
    import json as _json
    from pathlib import Path as _Path

    data = _json.loads(
        _Path(dataset_path).read_text(encoding="utf-8"))
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS c FROM evaluation_sample "
            "WHERE eval_type = 'matching' AND dataset_version = %s",
            (data.get("dataset_version", DATASET_VERSION),))
        if cur.fetchone()["c"] > 0:
            return 0
        inserted = 0
        profiles = {p["profile_id"]: p for p in data.get("profiles", [])}
        for p in data["pairs"]:
            profile = profiles[p["profile_id"]]
            gt = p["ground_truth"]
            cur.execute(
                """INSERT INTO evaluation_sample
                   (eval_type, input_payload, ground_truth, annotator,
                    annotated_at, dataset_version)
                   VALUES ('matching', %s, %s, %s, now(), %s)""",
                (_json.dumps({"id": p["id"], "profile_id": p["profile_id"],
                              "jd_text": p["jd_text"],
                              "jd_source": p["jd_source"],
                              "profile": profile}, ensure_ascii=False),
                 _json.dumps({"human_match_score":
                              gt["human_match_score"],
                              "strong_skills": gt["strong_skills"],
                              "weak_skills": gt["weak_skills"],
                              "missing_skills": gt["missing_skills"]},
                             ensure_ascii=False),
                 p.get("annotator", "user"), data.get("dataset_version",
                                                      DATASET_VERSION)))
            inserted += 1
    conn.commit()
    return inserted


def _materialize_candidate(conn, profile: dict) -> int:
    """E2 画像 → candidate（upsert：重建技能行；幂等）。"""
    from psycopg.types.json import Json
    from skillgap.ingest.extract import (
        load_alias_map, resolve_skill_id,
    )

    soft = dict(profile.get("soft_profile") or {})
    soft["e2_profile_id"] = profile["profile_id"]
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM candidate WHERE soft_profile->>'e2_profile_id' = %s",
            (profile["profile_id"],))
        row = cur.fetchone()
        if row:
            cid = row["id"]
            cur.execute("DELETE FROM candidate_skill WHERE candidate_id = %s",
                        (cid,))
        else:
            cur.execute(
                "INSERT INTO candidate (soft_profile) VALUES (%s) RETURNING id",
                (Json(soft),))
            cid = cur.fetchone()["id"]
        amap = load_alias_map(conn)
        for s in profile.get("skills", []):
            sid = resolve_skill_id(s["skill"], amap)
            if sid is None:
                raise ValueError(f"E2 画像技能未命中词表: {s['skill']}")
            cur.execute(
                """INSERT INTO candidate_skill
                   (candidate_id, skill_id, level, confidence, source_type)
                   VALUES (%s, %s, %s, %s, 'manual')
                   ON CONFLICT (candidate_id, skill_id) DO NOTHING""",
                (cid, sid, s["level"], s["confidence"]))
    conn.commit()
    return cid


def _materialize_job(conn, sample: dict) -> int:
    """E2 JD → job_id。job#N 直用；新文本（别名变体）插入 active 零技能
    job（content_hash 去重）——由调用方触发 LLM 回填。"""
    import re as _re
    from psycopg.types.json import Json
    from skillgap.ingest.normalize import content_hash
    from skillgap.ingest.sources import get_source

    src = sample["jd_source"]
    m = _re.search(r"job#(\d+)", src)
    if m:
        jid = int(m.group(1))
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM job WHERE id = %s", (jid,))
            if cur.fetchone() is None:
                raise ValueError(f"E2 引用的 job#{jid} 不存在")
        return jid
    chash = content_hash(sample["jd_text"])
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM job WHERE content_hash = %s", (chash,))
        row = cur.fetchone()
        if row:
            return row["id"]
        ds = get_source(conn, "company_career_page")
        cur.execute(
            """INSERT INTO job (title, job_category, market, language,
               raw_text, status, source_id, source_type, source_url,
               collected_at, content_hash, data_quality, parsed_metadata)
               VALUES (%s, 'agent_dev', 'china', 'zh', %s, 'active', %s,
                       %s, %s, now(), %s, 'auto_passed',
                       %s) RETURNING id""",
            ("E2 样本 JD", sample["jd_text"], ds["id"],
             ds["source_type"],
             f"https://example.com/e2/{sample['id']}", chash,
             Json({"e2_sample_id": sample["id"],
                   "extraction_status": "pending"})))
        jid = cur.fetchone()["id"]
    conn.commit()
    return jid


def run_e2(conn, extractor=None,
           dataset_version: str = DATASET_VERSION) -> dict:
    """端到端：加载样本 → 物化 → LLM 回填零技能样本（可选）→ 逐对
    match_score → 指标 → 对抗断言 → eval_run 留痕。"""
    import json as _json

    from skillgap.extract.analyzer import backfill_pending
    from skillgap.match.service import match_score

    with conn.cursor() as cur:
        cur.execute(
            """SELECT input_payload, ground_truth FROM evaluation_sample
               WHERE eval_type = 'matching' AND dataset_version = %s
               ORDER BY id""", (dataset_version,))
        rows = cur.fetchall()
    if not rows:
        raise ValueError(
            f"评测集 {dataset_version} 为空，请先运行 skillgap eval-e2"
            "（自动入库种子集）")

    # 物化（画像 upsert 幂等；新 JD 插入后统一回填）
    cand_cache: dict[str, int] = {}
    job_ids: list[int] = []
    samples = []
    for row in rows:
        s = row["input_payload"]
        samples.append((s, row["ground_truth"]))
        if s["profile_id"] not in cand_cache:
            cand_cache[s["profile_id"]] = _materialize_candidate(conn, s[
                "profile"])
        job_ids.append(_materialize_job(conn, s))
    if extractor is not None:
        backfill_pending(conn, extractor)

    pairs = []
    by_id = {}
    for (s, gt), jid in zip(samples, job_ids):
        result = match_score(conn, cand_cache[s["profile_id"]], jid)
        pair = {"system_score": result["overall_score"],
                "human_score": gt["human_match_score"],
                "system_groups": {k: set(result[f"{k}_skills"])
                                   for k in GROUPS},
                "human_groups": {k: set(gt[f"{k}_skills"]) for k in GROUPS}}
        pairs.append(pair)
        by_id[s["id"]] = pair

    adv = None
    if all(k in by_id for k in ("e2-001", "e2-002", "e2-003", "e2-008",
                                "e2-012")):
        adv = {
            "bare_claim_pair": (by_id["e2-001"]["system_score"],
                                by_id["e2-002"]["system_score"]),
            "unrelated_upper": 29,
            "unrelated_scores_max": by_id["e2-003"]["system_score"],
            "alias_pair": (by_id["e2-008"]["system_score"],
                           by_id["e2-012"]["system_score"]),
        }
    metrics = compute_metrics(pairs, adversarial=adv)
    from skillgap.match.scoring import SCORING_VERSION
    metrics["scoring_version"] = SCORING_VERSION

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO eval_run
               (eval_type, dataset_version, prompt_version, model, metrics,
                sample_size, verdict)
               VALUES ('matching', %s, %s, %s, %s, %s, %s)""",
            (dataset_version, metrics["scoring_version"], "deterministic",
             _json.dumps(metrics, ensure_ascii=False), len(pairs),
             metrics["verdict"]))
    conn.commit()
    return metrics
