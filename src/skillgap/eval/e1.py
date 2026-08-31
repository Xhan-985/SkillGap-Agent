"""E1 评测器（技能抽取质量回归——EVALUATION_PLAN §2）。

口径（预声明，跑分前冻结——§2.2/§2.3）：
- 匹配单位：alias 归一后的 taxonomy canonical_name；词表外抽取不进 P/R
  （归 new_skill_candidate 属抽取器职责，不计误报）
- 指标：micro P/R/F1——池化全部 (样本,技能) 决策，同名技能跨样本各计
  一次（样本内同名由 _dedupe_by_name 去重）；macro F1 逐技能平均
  （低频技能不隐身）；重要度准确率在名字命中的决策对上多重集匹配
- 证据可溯率：样本级——抽取成功且全部 evidence_text 可定位的样本占比；
  <100% 一票 block（纯程序判定，LLM 不参与指标计算——红线）
- 阈值：F1 与 Recall 同表——pass ≥0.85；warn ≥0.75；block <0.75
"""
from __future__ import annotations

import json
from collections import Counter

import psycopg

from skillgap.eval.seed import DATASET_VERSION
from skillgap.ingest.extract import (
    alias_map_from_db, locate_evidence, resolve_skill_id,
)

THRESHOLDS = {"pass": 0.85, "warn": 0.75}


def _dedupe_by_name(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """样本内同名去重（首个 importance 生效）；跨样本不去重（micro 决策）。"""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for name, importance in pairs:
        if name in seen:
            continue
        seen.add(name)
        out.append((name, importance))
    return out


def compute_metrics(extracted: list[tuple[str, str]],
                    truth: list[tuple[str, str]]) -> dict:
    """(canonical_name, importance) 决策列表 → 指标（纯函数，无 DB/LLM）。

    约定：空抽取 precision=1.0（无误报）；importance_accuracy 在名字
    命中的决策对上按 importance 多重集匹配计数。
    """
    ext_c = Counter(name for name, _ in extracted)
    tru_c = Counter(name for name, _ in truth)
    names = set(ext_c) | set(tru_c)
    tp = sum(min(ext_c[n], tru_c[n]) for n in names)
    precision = tp / len(extracted) if extracted else 1.0
    recall = tp / len(truth) if truth else 1.0
    f1 = 2 * precision * recall / (precision + recall) if tp else 0.0
    per_skill: list[float] = []
    for n in names:
        tp_n = min(ext_c[n], tru_c[n])
        p_n = tp_n / ext_c[n] if ext_c[n] else 1.0
        r_n = tp_n / tru_c[n] if tru_c[n] else 1.0
        per_skill.append(2 * p_n * r_n / (p_n + r_n) if tp_n else 0.0)
    imp_ok = 0
    for n in names:
        ext_i = Counter(i for m, i in extracted if m == n)
        tru_i = Counter(i for m, i in truth if m == n)
        imp_ok += sum(min(ext_i[k], tru_i[k])
                      for k in set(ext_i) | set(tru_i))
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "macro_f1": round(sum(per_skill) / len(per_skill), 4)
        if per_skill else 0.0,
        "importance_accuracy": round(imp_ok / tp, 4) if tp else 0.0,
    }


def verdict_for(metrics: dict) -> str:
    """阈值判定（跑分前冻结）。证据可溯率 <100% 一票 block。"""
    if metrics.get("evidence_rate", 1.0) < 1.0:
        return "block"
    f1 = metrics["f1"]
    recall = metrics.get("recall", 1.0)
    if f1 >= THRESHOLDS["pass"] and recall >= THRESHOLDS["pass"]:
        return "pass"
    if f1 >= THRESHOLDS["warn"] and recall >= THRESHOLDS["warn"]:
        return "warn"
    return "block"


def _extractor_model(extractor) -> str:
    model = getattr(extractor, "model_name", "")
    if not model:
        gateway = getattr(extractor, "gateway", None)
        model = getattr(getattr(gateway, "provider", None), "model", "")
    return model


def run_e1(conn: psycopg.Connection, extractor,
           prompt_version: str | None = None,
           dataset_version: str = DATASET_VERSION) -> dict:
    """端到端评测：加载标注集 → 逐样本抽取 → 指标 → 判定 → 入 eval_run。

    抽取器只需满足 SkillExtractor 协议（extract(jd_text)）；
    失败样本计为空抽取（拉低 recall），不中断评测。
    """
    if prompt_version is None:
        gateway = getattr(extractor, "gateway", None)
        prompt_version = (getattr(gateway, "prompt_version", None)
                          or "fake-v0")
    model = _extractor_model(extractor)

    with conn.cursor() as cur:
        cur.execute(
            """SELECT input_payload, ground_truth FROM evaluation_sample
               WHERE eval_type = 'skill_extraction'
                 AND dataset_version = %s ORDER BY id""",
            (dataset_version,))
        rows = cur.fetchall()
    if not rows:
        raise ValueError(
            f"评测集 {dataset_version} 为空，请运行 skillgap eval-e1"
            "（自动入库种子集）")

    amap = alias_map_from_db(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT id, canonical_name FROM skill")
        sid_to_name = {r["id"]: r["canonical_name"] for r in cur.fetchall()}

    pooled_ext: list[tuple[str, str]] = []
    pooled_tru: list[tuple[str, str]] = []
    n_evidence_ok = 0
    failures = 0
    for row in rows:
        jd_text = row["input_payload"]["jd_text"]
        truth = row["ground_truth"] or {}
        # micro：池化 (样本,技能) 决策——样本内同名去重，跨样本不去重
        pooled_tru.extend(_dedupe_by_name([
            (s["canonical_name"], s.get("importance", "must_have"))
            for s in truth.get("skills", [])]))
        try:
            anns = extractor.extract(jd_text)
        except Exception:
            failures += 1
            continue
        if all(locate_evidence(jd_text, a.evidence_text) for a in anns):
            n_evidence_ok += 1
        ext_pairs = []
        for a in anns:
            sid = resolve_skill_id(a.raw_name, amap)
            if sid is None:
                continue          # 词表外：不进 P/R（候选表属抽取器职责）
            ext_pairs.append((sid_to_name[sid], a.importance))
        pooled_ext.extend(_dedupe_by_name(ext_pairs))

    metrics = compute_metrics(pooled_ext, pooled_tru)
    metrics["evidence_rate"] = round(n_evidence_ok / len(rows), 4)
    metrics["extraction_failures"] = failures
    verdict = verdict_for(metrics)

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO eval_run
               (eval_type, dataset_version, prompt_version, model,
                metrics, sample_size, verdict)
               VALUES ('skill_extraction', %s, %s, %s, %s, %s, %s)""",
            (dataset_version, prompt_version, model,
             json.dumps(metrics, ensure_ascii=False), len(rows), verdict))
    conn.commit()
    return {"dataset_version": dataset_version,
            "prompt_version": prompt_version, "model": model,
            "sample_size": len(rows), "verdict": verdict, **metrics}
