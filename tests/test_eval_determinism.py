"""评测确定性与一致性（Phase 9 T2 劣化演练 + T4 零漂移/taxonomy）。

T2（C4 轨①，进 pytest 即进 CI）：
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

T4（D4 零漂移 + D5 taxonomy 一致性）：
- D4：run_e2/run_e3 同一 fixture 市场连跑两次，两次 metrics dict
  **完全相等**（E1 排除——LLM 非确定性由 C5 方差演练覆盖）
- D5：E2/E3 标注集里出现的技能名 ⊆ 词表 canonical_name（文件级，
  读 JSON + taxonomy CSV，不触 DB——CI 无库也能跑；E1 两版已由
  test_eval_seed.py::test_ground_truth_uses_taxonomy_canonical_names 覆盖）

真实库手动演练（C4 轨②：改权重 → eval-gate exit 1 → 复原）记入
PHASE_9_REVIEW，不在本文件。
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

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
    """三岗位 fixture 市场 + 标注集入库（jd_source 回填真实 job id；
    content_hash 与 pair jd_text 对齐——E2 物化按内容寻址）。"""
    from skillgap.ingest.normalize import content_hash
    sid = _source(clean_db)
    j1 = _insert_job(clean_db, **_job_kwargs(
        sid, content_hash=content_hash("a" * 200)))
    j2 = _insert_job(clean_db, **_job_kwargs(
        sid, content_hash=content_hash("b" * 200)))
    j3 = _insert_job(clean_db, **_job_kwargs(
        sid, content_hash=content_hash("c" * 200)))
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


# ---------- T4 / D4：零漂移（同版本重跑确定性指标完全相等） ----------

def test_run_e2_zero_drift_double_run(clean_db, _drill_market):
    """E2 双跑：同一 fixture 市场连跑两次，两次 metrics dict 完全相等
    （ROADMAP"同版本重跑确定性指标零漂移"；E1 排除——LLM 非确定性
    由 C5 方差演练覆盖）。"""
    m1 = run_e2(clean_db, extractor=None, dataset_version=DATASET_VERSION)
    m2 = run_e2(clean_db, extractor=None, dataset_version=DATASET_VERSION)
    assert m1 == m2
    # 留痕两条且库内指标一致（强于返回值相等：JSONB 回读无损）
    rows = clean_db.execute(
        "SELECT metrics FROM eval_run WHERE eval_type='matching' "
        "ORDER BY id").fetchall()
    assert len(rows) == 2
    assert rows[0]["metrics"] == rows[1]["metrics"]


def test_run_e3_zero_drift_double_run(clean_db, tmp_path):
    """E3 双跑：同市场同标注集连跑两次，metrics dict 完全相等
    （画像 upsert 幂等 + recommend 规则确定 → 零漂移）。"""
    from skillgap.eval.e3 import run_e3, seed_eval3
    from tests.test_eval_e3_runner import _DATASET as E3_DATASET
    from tests.test_recommend_service_fixtures import seed_market

    seed_market(clean_db)
    path = tmp_path / "e3_zero.json"
    path.write_text(json.dumps(E3_DATASET, ensure_ascii=False),
                    encoding="utf-8")
    assert seed_eval3(clean_db, str(path)) == len(E3_DATASET["cases"])

    m1 = run_e3(clean_db, dataset_version=E3_DATASET["dataset_version"])
    m2 = run_e3(clean_db, dataset_version=E3_DATASET["dataset_version"])
    assert m1 == m2
    assert m1["n_cases"] == len(E3_DATASET["cases"])   # 非空跑（防 0==0 自欺）


# ---------- T4 / D5：taxonomy 一致性（标注集技能 ⊆ 词表，文件级） ----------

REPO = Path(__file__).resolve().parents[1]
EVAL_DIR = REPO / "data" / "eval"
TAXONOMY_CSV = (REPO / "src" / "skillgap" / "taxonomy" / "data"
                / "skills_v1.csv")


def _canonical_names() -> set[str]:
    """词表 canonical_name 集合（文件级读取，不触 DB）。"""
    with TAXONOMY_CSV.open(encoding="utf-8-sig") as f:
        return {row["canonical_name"].strip() for row in csv.DictReader(f)
                if row["canonical_name"].strip()}


def test_e2_seed_skills_within_taxonomy():
    """E2 标注集：画像技能 + 三组判定（strong/weak/missing）⊆ 词表
    （EVALUATION_PLAN §6 词表与评测集一致性由 CI 检查）。"""
    canon = _canonical_names()
    data = json.loads(
        (EVAL_DIR / "e2_seed_v1.json").read_text(encoding="utf-8"))
    names = {s["skill"] for p in data["profiles"] for s in p["skills"]}
    for pair in data["pairs"]:
        gt = pair["ground_truth"]
        for k in ("strong_skills", "weak_skills", "missing_skills"):
            names |= set(gt.get(k, []))
    outside = names - canon
    assert not outside, f"E2 标注集词表外技能: {sorted(outside)}"


def test_e3_seed_skills_within_taxonomy():
    """E3 标注集：画像技能 + 相关性标注键（含 rel=0 的"已具备"技能）
    ⊆ 词表。"""
    canon = _canonical_names()
    data = json.loads(
        (EVAL_DIR / "e3_seed_v1.json").read_text(encoding="utf-8"))
    names = {s["skill"] for c in data["cases"]
             for s in c["profile"]["skills"]}
    for c in data["cases"]:
        names |= set(c["relevance"])
    outside = names - canon
    assert not outside, f"E3 标注集词表外技能: {sorted(outside)}"
