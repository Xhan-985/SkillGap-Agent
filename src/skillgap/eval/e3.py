"""E3 评测器（推荐质量回归——EVALUATION_PLAN §4）。

口径（预声明，跑分前冻结）：
- nDCG@5：系统 Top5 排序 × 标注相关性（2/1/0 三档，增益 2^rel−1）
- Precision@5：Top5 中标注 ≥1 的比例
- Hit Rate@3：标注=2 的技能至少一个进系统 Top3（无必补标注不惩罚）
- 建议覆盖率（coverage）：标注 ≥1 技能出现在优先级清单的比例
- 阈值（起步线，标注薄样本）：nDCG ≥0.5 pass / ≥0.35 warn / 其余 block
- 红线：指标计算零 LLM；系统排序由 recommend() 规则产出

数据流（计划 D9，复用 E1/E2 模式）：seed_eval3 幂等入
evaluation_sample(eval_type='recommendation') → run_e3 物化画像
（复用 e2 的 _materialize_candidate，e2_profile_id 标记）→ 逐画像
recommend() → 指标 → eval_run 留痕。
"""
from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

E3_THRESHOLDS = {"ndcg": {"pass": 0.5, "warn": 0.35}}
DATASET_VERSION = "e3-v1"
DATASET_PATH = "data/eval/e3_seed_v1.json"

_REL_HIGH = ("必补", "高价值")
_REL_MID = ("值得补",)


def relevance_of(note: str, skill: str) -> int:
    """标注文本 → 相关性三档（2=必补 / 1=值得补 / 0=低价值）。"""
    text = note or ""
    if any(k in text for k in _REL_HIGH):
        return 2
    if any(k in text for k in _REL_MID):
        return 1
    return 0


def dcg(rels: Sequence[int]) -> float:
    """增益 2^rel−1（计划 D7），对数折减。"""
    return sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))


def ndcg_at_k(sys_rels: Sequence[int], ideal_rels: Sequence[int],
              k: int = 5) -> float:
    """nDCG：sys_rels 为系统排序对齐的相关性；ideal 为标注全集降序。"""
    if not sys_rels or not ideal_rels:
        return 0.0
    ideal = sorted(ideal_rels, reverse=True)[:k]
    d_ideal = dcg(ideal)
    return dcg(list(sys_rels)[:k]) / d_ideal if d_ideal > 0 else 0.0


def precision_at_k(system_top: Sequence[str],
                   relevance: Mapping[str, int], k: int = 5) -> float:
    top = list(system_top)[:k]
    if not top:
        return 0.0
    hits = sum(1 for s in top if relevance.get(s, 0) >= 1)
    return hits / len(top)


def hit_rate_at_k(system_top: Sequence[str],
                  relevance: Mapping[str, int], k: int = 3) -> float:
    """必补技能（rel=2）是否至少一个进 Top-k（单查询二值）。"""
    top = set(list(system_top)[:k])
    must = {s for s, r in relevance.items() if r == 2}
    if not must:
        return 1.0        # 无必补标注：视为命中（不惩罚）
    return 1.0 if must & top else 0.0


def _verdict(metrics: dict) -> str:
    th = E3_THRESHOLDS["ndcg"]
    v = metrics["ndcg@5"]
    if v >= th["pass"]:
        return "pass"
    if v >= th["warn"]:
        return "warn"
    return "block"


# ==================== 评测器（DB 装配层） ====================

def read_dataset_version(dataset_path: str = DATASET_PATH) -> str:
    """标注集文件 → dataset_version（CLI 传递给 run_e3 保持一致）。"""
    path = Path(dataset_path)
    if not path.exists():
        raise ValueError(f"标注集不存在：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("dataset_version", DATASET_VERSION)


def seed_eval3(conn, dataset_path: str = DATASET_PATH) -> int:
    """E3 标注集幂等入库（evaluation_sample eval_type='recommendation'）。"""
    path = Path(dataset_path)
    if not path.exists():
        raise ValueError(f"标注集不存在：{path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    version = data.get("dataset_version", DATASET_VERSION)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS c FROM evaluation_sample "
            "WHERE eval_type = 'recommendation' AND dataset_version = %s",
            (version,))
        if cur.fetchone()["c"] > 0:
            return 0
        inserted = 0
        for case in data["cases"]:
            cur.execute(
                """INSERT INTO evaluation_sample
                   (eval_type, input_payload, ground_truth, annotator,
                    annotated_at, dataset_version)
                   VALUES ('recommendation', %s, %s, %s, now(), %s)""",
                (json.dumps({"case_id": case["case_id"],
                             "profile_id": case["profile_id"],
                             "time_budget_days": case.get(
                                 "time_budget_days", 14),
                             "market": case.get("market", "china"),
                             "profile": case["profile"]},
                            ensure_ascii=False),
                 json.dumps({"relevance": case["relevance"]},
                            ensure_ascii=False),
                 case.get("annotator", "user"), version))
            inserted += 1
    conn.commit()
    return inserted


def run_e3(conn, gateway=None, dataset_version: str = DATASET_VERSION,
           judge_provider=None) -> dict:
    """端到端：加载样本 → 物化画像（复用 e2）→ 逐画像 recommend() →
    指标 →（可选）LLM-as-judge → eval_run 留痕。

    红线：排序指标全部来自 recommend() 规则产出；judge 为 Warn 级参考
    信号（EVALUATION_PLAN §4.2），**不参与 verdict**；单条 judge 失败
    跳过不中断（报告明示覆盖率）。
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT input_payload, ground_truth FROM evaluation_sample
               WHERE eval_type = 'recommendation' AND dataset_version = %s
               ORDER BY id""", (dataset_version,))
        rows = cur.fetchall()
    if not rows:
        raise ValueError(
            f"评测集 {dataset_version} 为空，请先运行 skillgap eval-e3"
            "（自动入库种子集）")

    from skillgap.eval.e2 import _materialize_candidate
    from skillgap.recommend.roi import ROI_VERSION
    from skillgap.recommend.service import recommend

    ndcgs, precs, hits, covs = [], [], [], []
    per_case = []
    recs = []                       # judge pass 复用（不重跑 recommend）
    for row in rows:
        case = row["input_payload"]
        gt = row["ground_truth"]
        cid = _materialize_candidate(conn, case["profile"])
        rec = recommend(conn, cid,
                        time_budget_days=case.get("time_budget_days", 14),
                        market=case.get("market", "china"))
        recs.append((case, rec))
        top = [it["skill"] for it in rec["priority_items"]]
        rel = {s: relevance_of(note, s)
               for s, note in gt["relevance"].items()}
        # 系统未见技能补 0；ideal = 标注相关性降序（含未推荐的）
        sys_rels = [rel.get(s, 0) for s in top]
        ideal_all = sorted(rel.values(), reverse=True)
        ndcgs.append(ndcg_at_k(sys_rels, ideal_all))
        precs.append(precision_at_k(top, rel))
        hits.append(hit_rate_at_k(top, rel))
        rec_set = {it["skill"] for it in rec["priority_items"]}
        labeled = [s for s, r in rel.items() if r >= 1]
        covs.append(len([s for s in labeled if s in rec_set]) / len(labeled)
                    if labeled else 1.0)
        per_case.append({"case_id": case.get("case_id"),
                         "ndcg@5": round(ndcgs[-1], 4)})

    metrics = {
        "ndcg@5": round(sum(ndcgs) / len(ndcgs), 4),
        "precision@5": round(sum(precs) / len(precs), 4),
        "hit_rate@3": round(sum(hits) / len(hits), 4),
        "coverage": round(sum(covs) / len(covs), 4),
        "n_cases": len(rows),
        "per_case": per_case,
    }

    if judge_provider is not None:
        from skillgap.eval.judge import RUBRIC_VERSION, judge_recommendation
        scores, judged_cases = [], []
        for case, rec in recs:
            try:
                j = judge_recommendation(judge_provider, rec)
            except Exception:      # 失败跳过（计划风险条款）
                continue
            scores.append(j["score"])
            judged_cases.append(case.get("case_id"))
        metrics["judge"] = {
            "mean": round(sum(scores) / len(scores), 2) if scores else None,
            "n_judged": len(scores),
            "rubric_version": RUBRIC_VERSION,
            "judged_cases": judged_cases,
        }

    metrics["verdict"] = _verdict(metrics)

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO eval_run
               (eval_type, dataset_version, prompt_version, model, metrics,
                sample_size, verdict)
               VALUES ('recommendation', %s, %s, %s, %s, %s, %s)""",
            (dataset_version, ROI_VERSION, "deterministic",
             json.dumps(metrics, ensure_ascii=False), len(rows),
             metrics["verdict"]))
    conn.commit()
    return metrics
