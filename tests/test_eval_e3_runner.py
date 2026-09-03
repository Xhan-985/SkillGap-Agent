"""E3 runner 测试（零 LLM：seed 幂等入库 + 画像物化复用 e2 +
recommend() 规则跑分 + eval_run 留痕）。"""
import json

import pytest

from skillgap.eval.e3 import run_e3, seed_eval3
from tests.test_recommend_service_fixtures import seed_market

_DATASET = {
    "dataset_version": "e3-test",
    "cases": [
        # RAG 4 / Python 3：缺口 MCP（req 5）+ Docker（req 2）
        # ROI：MCP 0.5×5/2=1.25 > Docker 0.5×2/1=1.0 → 系统序 [MCP, Docker]
        {"case_id": "e3t-001", "profile_id": "PT",
         "time_budget_days": 14, "market": "china",
         "profile": {"profile_id": "PT", "label": "RAG 强缺工程",
                     "skills": [
                         {"skill": "RAG", "level": 4, "confidence": 0.9},
                         {"skill": "Python", "level": 3, "confidence": 0.6}],
                     "soft_profile": {"experience_years": 2}},
         "relevance": {"MCP": "必补：市场高频大缺口", "Docker": "值得补",
                       "RAG": "已具备", "Python": "已具备"}},
        # 仅 Docker 5：缺口 Python(3)/MCP(5)/RAG(4)
        # ROI：Python 1.5 > MCP 1.25 > RAG 1.0 → 系统序 [Python, MCP, RAG]
        {"case_id": "e3t-002", "profile_id": "PF",
         "time_budget_days": 14, "market": "china",
         "profile": {"profile_id": "PF", "label": "仅工程",
                     "skills": [
                         {"skill": "Docker", "level": 5, "confidence": 0.9}],
                     "soft_profile": {"experience_years": 3}},
         "relevance": {"MCP": "必补：市场高频大缺口", "RAG": "值得补",
                       "Python": "值得补"}},
    ],
}


@pytest.fixture
def _dataset_file(tmp_path):
    path = tmp_path / "e3_test.json"
    path.write_text(json.dumps(_DATASET, ensure_ascii=False), encoding="utf-8")
    return path


def test_seed_eval3_idempotent(clean_db, _dataset_file):
    assert seed_eval3(clean_db, str(_dataset_file)) == 2
    assert seed_eval3(clean_db, str(_dataset_file)) == 0       # 幂等
    n = clean_db.execute(
        "SELECT count(*) AS n FROM evaluation_sample "
        "WHERE eval_type='recommendation'").fetchone()["n"]
    assert n == 2


def test_seed_eval3_missing_file_raises(clean_db, tmp_path):
    with pytest.raises(ValueError, match="不存在"):
        seed_eval3(clean_db, str(tmp_path / "nope.json"))


def test_run_e3_end_to_end(clean_db, _dataset_file):
    """零 LLM 全链路：物化画像（复用 e2）→ recommend 规则 → 指标 +
    eval_run 留痕。"""
    seed_market(clean_db)             # 32 岗市场（过 ADR-008 守门）
    seed_eval3(clean_db, str(_dataset_file))
    metrics = run_e3(clean_db, dataset_version="e3-test")

    assert metrics["n_cases"] == 2
    assert metrics["per_case"][0]["ndcg@5"] == 1.0     # e3t-001 序完全一致
    assert 0.7 < metrics["per_case"][1]["ndcg@5"] < 1.0
    assert metrics["precision@5"] == 1.0
    assert metrics["hit_rate@3"] == 1.0               # MCP 均进 Top3
    assert metrics["coverage"] == 1.0
    assert metrics["ndcg@5"] > 0.5                    # 起步线上 → pass
    assert metrics["verdict"] == "pass"
    # eval_run 留痕
    row = clean_db.execute(
        "SELECT metrics, verdict FROM eval_run "
        "WHERE eval_type='recommendation' AND dataset_version='e3-test'"
    ).fetchone()
    assert row is not None
    assert row["verdict"] == "pass"
    assert row["metrics"]["n_cases"] == 2


def test_run_e3_candidate_materialize_upsert(clean_db, _dataset_file):
    """重复跑分：画像 upsert 不重复建 candidate；eval_run 每次留痕。"""
    seed_market(clean_db)
    seed_eval3(clean_db, str(_dataset_file))
    run_e3(clean_db, dataset_version="e3-test")
    run_e3(clean_db, dataset_version="e3-test")
    n = clean_db.execute(
        "SELECT count(*) AS n FROM candidate "
        "WHERE soft_profile->>'e2_profile_id' IN ('PT', 'PF')").fetchone()["n"]
    assert n == 2
    rows = clean_db.execute(
        "SELECT count(*) AS n FROM eval_run "
        "WHERE eval_type='recommendation'").fetchone()["n"]
    assert rows == 2


def test_run_e3_empty_dataset_raises(clean_db):
    with pytest.raises(ValueError, match="为空"):
        run_e3(clean_db, dataset_version="not-exist")
