"""劣化演练自动化（Phase 9 T2——计划 C4 轨①：进 pytest 即进 CI）。

证明"PR 带劣化会被拦"的可重复路径：
monkeypatch 改坏 match.scoring.WEIGHTS（coverage→0.0，**不动 SCORING_VERSION**
——模拟不升版的坏改动，版本三元组失守时由 gate 兜底）→ run_e2 在
fixture 市场上跑分 → ρ/MAE 崩 → eval_run verdict=block → gate 汇总
（E1/E3 健康 pass 在场）→ 任一 block → 整体 block → exit 1。

反向对照（防测试自欺）：同一 fixture 市场不改权重 → 同路径 verdict=pass →
gate exit 0——证明 block 来自权重劣化而非 fixture 本身。

fixture 市场设计（劣化必须让**排序翻转**，而非仅分数下降）：
- J1 纯 nice 全满足：coverage 0.95 / importance 0.5（无 must 中性）
- J2 单 must 满足 + 3 nice 缺失：coverage 0.475 / importance 1.0
- J3 单 must 满足 + 4 nice 缺失：coverage 0.407 / importance 1.0
正常权重下 coverage 主导（J1 > J2 > J3，与人工分一致）；coverage 清零后
importance 主导（J2=J3 > J1，排序翻转）→ ρ 崩至负值。三组技能判定
（strong/weak/missing）不依赖权重 → jaccard/prf 不变，block 纯来自分数。

真实库手动演练（C4 轨②：改权重 → eval-gate exit 1 → 复原）记入
PHASE_9_REVIEW，不在本文件。
"""
from __future__ import annotations

import json

import pytest

from skillgap.eval.e2 import run_e2, seed_eval2
from skillgap.eval.gate import apply_gate, gate_exit_code, latest_runs
from skillgap.match.scoring import SCORING_VERSION
from tests.test_schema import _insert_job, _job_kwargs, _source

DATASET_VERSION = "e2-drill"

# 画像：三技能全 5 级高置信——evidence 恒 0.9，聚焦 coverage/importance 对比
_DATASET = {
    "dataset_version": DATASET_VERSION,
    "profiles": [
        {"profile_id": "PT",
         "soft_profile": {"experience_years": 3},
         "skills": [{"skill": "RAG", "level": 5, "confidence": 0.9},
                    {"skill": "Python", "level": 5, "confidence": 0.9},
                    {"skill": "Docker", "level": 5, "confidence": 0.9}]},
    ],
    # 人工分 = 正常权重的系统分取整（MAE≈0.3）；三组标注与系统判定一致
    "pairs": [
        {"id": "d-101", "profile_id": "PT", "jd_text": "a" * 200,
         "jd_source": "job#{J1}",
         "ground_truth": {"human_match_score": 78,
                          "strong_skills": ["RAG", "Python", "Docker"],
                          "weak_skills": [], "missing_skills": []}},
        {"id": "d-102", "profile_id": "PT", "jd_text": "b" * 200,
         "jd_source": "job#{J2}",
         "ground_truth": {"human_match_score": 69,
                          "strong_skills": ["RAG"], "weak_skills": [],
                          "missing_skills": ["Go", "Java", "Kubernetes"]}},
        {"id": "d-103", "profile_id": "PT", "jd_text": "c" * 200,
         "jd_source": "job#{J3}",
         "ground_truth": {"human_match_score": 66,
                          "strong_skills": ["RAG"], "weak_skills": [],
                          "missing_skills": ["Go", "Java", "Kubernetes",
                                             "LangGraph"]}},
    ],
}


def _req(clean_db, job_id, skill, importance, intensity):
    sid = clean_db.execute(
        "SELECT id FROM skill WHERE canonical_name = %s", (skill,)
    ).fetchone()["id"]
    clean_db.execute(
        """INSERT INTO job_skill (job_id, skill_id, importance, intensity,
           evidence_text, extracted_by) VALUES (%s, %s, %s, %s, %s, 'manual')""",
        (job_id, sid, importance, intensity, f"要求 {skill}"))
    clean_db.commit()


@pytest.fixture()
def _drill_market(clean_db, tmp_path):
    """三岗位 fixture 市场 + 标注集入库（jd_source 回填真实 job id）。"""
    sid = _source(clean_db)
    j1 = _insert_job(clean_db, **_job_kwargs(sid, content_hash="h-d1"))
    j2 = _insert_job(clean_db, **_job_kwargs(sid, content_hash="h-d2"))
    j3 = _insert_job(clean_db, **_job_kwargs(sid, content_hash="h-d3"))
    # J1：纯 nice 全满足（coverage 0.95 / importance 0.5）
    for s in ("RAG", "Python", "Docker"):
        _req(clean_db, j1, s, "nice_to_have", "熟悉")
    # J2：单 must 满足 + 3 nice 缺失（coverage 0.475 / importance 1.0）
    _req(clean_db, j2, "RAG", "must_have", "熟练")
    for s in ("Go", "Java", "Kubernetes"):
        _req(clean_db, j2, s, "nice_to_have", "熟悉")
    # J3：单 must 满足 + 4 nice 缺失（coverage 0.407 / importance 1.0）
    _req(clean_db, j3, "RAG", "must_have", "熟悉")
    for s in ("Go", "Java", "Kubernetes", "LangGraph"):
        _req(clean_db, j3, s, "nice_to_have", "熟悉")

    data = json.loads(json.dumps(_DATASET, ensure_ascii=False))
    data["pairs"][0]["jd_source"] = f"job#{j1}"
    data["pairs"][1]["jd_source"] = f"job#{j2}"
    data["pairs"][2]["jd_source"] = f"job#{j3}"
    path = tmp_path / "e2_drill.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert seed_eval2(clean_db, str(path)) == 3


def _insert_healthy_runs(clean_db):
    """E1/E3 健康 pass 在场——block 必须穿透汇总（任一 block → 整体）。"""
    with clean_db.cursor() as cur:
        for et in ("skill_extraction", "recommendation"):
            cur.execute(
                """INSERT INTO eval_run (eval_type, dataset_version,
                   prompt_version, model, metrics, sample_size, verdict)
                   VALUES (%s, 'v', 'p', 'm', '{}'::jsonb, 1, 'pass')""",
                (et,))
    clean_db.commit()


# ---------- 劣化演练（C4 轨①：自动化证明） ----------

def test_degradation_drill_weight_corruption_blocks(clean_db, _drill_market,
                                                    monkeypatch):
    """权重改坏（coverage→0.0，不升版）→ ρ/MAE 崩 → verdict=block →
    gate（E1/E3 pass 在场）整体 block → exit 1。"""
    from skillgap.match import scoring

    snapshot = dict(scoring.WEIGHTS)
    monkeypatch.setitem(scoring.WEIGHTS, "coverage", 0.0)   # 坏 PR

    metrics = run_e2(clean_db, extractor=None, dataset_version=DATASET_VERSION)
    assert metrics["verdict"] == "block"
    assert metrics["spearman"] < 0.5          # 排序翻转（预测 ≈ -0.866）
    assert metrics["mae"] > 20                # 分数整体崩塌（预测 ≈ 27.2）
    # 坏改动不动版本号——版本三元组失守，gate 是最后防线
    assert metrics["scoring_version"] == SCORING_VERSION

    _insert_healthy_runs(clean_db)
    result = apply_gate(latest_runs(clean_db))
    assert result["overall"] == "block"
    assert result["per_type"]["matching"]["verdict"] == "block"
    assert gate_exit_code(result) == 1                      # CI 阻断合并

    # 复原检查（计划风险表）：monkeypatch 回滚后权重原样，不污染其他测试
    monkeypatch.undo()
    assert scoring.WEIGHTS == snapshot


def test_degradation_drill_control_same_path_passes(clean_db, _drill_market):
    """反向对照（防自欺）：不改权重，同一 fixture 市场同路径 →
    pass → gate exit 0——block 只能来自权重劣化。"""
    metrics = run_e2(clean_db, extractor=None, dataset_version=DATASET_VERSION)
    assert metrics["verdict"] == "pass"
    assert metrics["spearman"] == pytest.approx(1.0)   # 排序与人工完全一致
    assert metrics["mae"] <= 12
    assert metrics["jaccard"] == pytest.approx(1.0)    # 三组判定全对
    assert metrics["prf_micro"]["f1"] == pytest.approx(1.0)

    _insert_healthy_runs(clean_db)
    result = apply_gate(latest_runs(clean_db))
    assert result["overall"] == "pass"
    assert gate_exit_code(result) == 0
