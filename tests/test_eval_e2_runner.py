"""E2 runner 物化/跑分机制测试（Fake 物化：content_hash 内容寻址复用 +
别名 JD 手工技能，零 LLM——真实 LLM 物化在 eval-e2 实跑中验证）。"""
import json

import pytest

from skillgap.eval.e2 import run_e2, seed_eval2
from skillgap.match.scoring import SCORING_VERSION
from tests.test_schema import _insert_job, _job_kwargs, _source

# 最小数据集：3 对——job# 直用、job# 直用（无关 JD 上界）、别名 JD
_DATASET = {
    "dataset_version": "e2-test",
    "profiles": [
        {"profile_id": "PT",
         "soft_profile": {"experience_years": 3},
         "skills": [{"skill": "RAG", "level": 4, "confidence": 0.9},
                    {"skill": "Python", "level": 3, "confidence": 0.4}]},
    ],
    "pairs": [
        {"id": "t-001", "profile_id": "PT", "jd_text": "x" * 200,
         "jd_source": "job#{J1}",
         "ground_truth": {"human_match_score": 60,
                          "strong_skills": ["RAG"], "weak_skills": ["Python"],
                          "missing_skills": ["Docker"]}},
        {"id": "t-003", "profile_id": "PT", "jd_text": "y" * 200,
         "jd_source": "job#{J2}",
         "ground_truth": {"human_match_score": 25,
                          "strong_skills": [], "weak_skills": [],
                          "missing_skills": ["Docker", "Go", "Kubernetes"]}},
        {"id": "t-012", "profile_id": "PT", "jd_text": "z" * 200,
         "jd_source": "别名变体样本（非 job#）",
         "ground_truth": {"human_match_score": 60,
                          "strong_skills": ["RAG"], "weak_skills": ["Python"],
                          "missing_skills": ["Docker"]}},
    ],
}


def _mk_job(clean_db, **kw):
    sid = _source(clean_db)
    kw.setdefault("content_hash", kw.pop("_hash", "h-runner"))
    return _insert_job(clean_db, **_job_kwargs(sid, **kw))


def _req(clean_db, job_id, skill, importance="must_have", intensity="熟悉"):
    sid = clean_db.execute(
        "SELECT id FROM skill WHERE canonical_name = %s", (skill,)
    ).fetchone()["id"]
    clean_db.execute(
        """INSERT INTO job_skill (job_id, skill_id, importance, intensity,
           evidence_text, extracted_by) VALUES (%s, %s, %s, %s, %s, 'manual')""",
        (job_id, sid, importance, intensity, f"要求 {skill}"))
    clean_db.commit()


@pytest.fixture
def _dataset_file(clean_db, tmp_path):
    """J1/J2 真实入库；别名 JD 由 run_e2 内部插入（active 零技能）+
    本 fixture 预置同 content_hash 的已抽取版本模拟 LLM 回填完成。"""
    from skillgap.ingest.normalize import content_hash

    j1 = _mk_job(clean_db, _hash=content_hash("x" * 200))
    j2 = _mk_job(clean_db, _hash=content_hash("y" * 200))
    _req(clean_db, j1, "RAG", "must_have", "熟练")
    _req(clean_db, j1, "Python", "must_have", "熟悉")
    _req(clean_db, j1, "Docker", "nice_to_have", "熟悉")
    _req(clean_db, j2, "Docker", "must_have", "熟练")
    _req(clean_db, j2, "Go", "must_have", "熟练")
    _req(clean_db, j2, "Kubernetes", "must_have", "熟悉")
    # 别名 JD 预置（模拟 LLM 回填完成；技能同 J1 → 与 t-001 同判定）
    j12 = _mk_job(clean_db, _hash=content_hash("z" * 200))
    _req(clean_db, j12, "RAG", "must_have", "熟练")
    _req(clean_db, j12, "Python", "must_have", "熟悉")
    _req(clean_db, j12, "Docker", "nice_to_have", "熟悉")
    data = json.loads(json.dumps(_DATASET, ensure_ascii=False))
    data["pairs"][0]["jd_source"] = f"job#{j1}"
    data["pairs"][1]["jd_source"] = f"job#{j2}"
    path = tmp_path / "e2_test.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_seed_eval2_idempotent(clean_db, _dataset_file):
    assert seed_eval2(clean_db, str(_dataset_file)) == 3
    assert seed_eval2(clean_db, str(_dataset_file)) == 0       # 幂等
    n = clean_db.execute(
        "SELECT count(*) AS n FROM evaluation_sample "
        "WHERE eval_type='matching'").fetchone()["n"]
    assert n == 3


def test_materialize_job_id_drift_guard(clean_db):
    """id 漂移防护（2026-09-22 卷丢失事故回归锚定）：jd_source 的 job#N
    失效/指向他岗时，按 jd_text 的 content_hash 复用正确岗位——旧实现
    id 直用曾在库重建后致 E2 24/24 对错配（ρ 0.84→0.45 假性 block）。"""
    from skillgap.eval.e2 import _materialize_job
    from skillgap.ingest.normalize import content_hash

    sid = _source(clean_db)
    j1 = _insert_job(clean_db, **_job_kwargs(
        sid, content_hash=content_hash("x" * 200)))
    sample = {"id": "t-drift", "jd_text": "x" * 200,
              "jd_source": "job#424242（重建后原 id 已指向他岗）"}
    assert _materialize_job(clean_db, sample) == j1


def test_run_e2_end_to_end_fake_materialization(clean_db, _dataset_file):
    """零 LLM 全链路：物化画像 → job# 复用 → 别名 JD content_hash 复用 →
    match_score → 指标 + eval_run 留痕。"""
    seed_eval2(clean_db, str(_dataset_file))
    metrics = run_e2(clean_db, extractor=None, dataset_version="e2-test")
    assert metrics["sample_size"] == 3
    assert metrics["scoring_version"] == SCORING_VERSION
    assert metrics["spearman"] == pytest.approx(1.0)   # 三对排序完美一致
    assert metrics["jaccard"] == pytest.approx(1.0)    # 三组判定全对
    assert metrics["prf_micro"]["f1"] == pytest.approx(1.0)
    # eval_run 留痕
    row = clean_db.execute(
        "SELECT metrics, verdict FROM eval_run "
        "WHERE eval_type='matching' AND dataset_version='e2-test'"
    ).fetchone()
    assert row is not None
    assert row["verdict"] in ("pass", "warn", "block")
    assert row["metrics"]["sample_size"] == 3


def test_run_e2_empty_dataset_raises(clean_db):
    with pytest.raises(ValueError, match="为空"):
        run_e2(clean_db, dataset_version="not-exist")


def test_materialize_candidate_upsert(clean_db, _dataset_file):
    """画像重复物化：技能行重建不重复（UNIQUE + delete-then-insert）。"""
    seed_eval2(clean_db, str(_dataset_file))
    from skillgap.eval.e2 import _materialize_candidate
    s = clean_db.execute(
        "SELECT input_payload->'profile' AS p FROM evaluation_sample "
        "WHERE eval_type='matching' LIMIT 1").fetchone()["p"]
    c1 = _materialize_candidate(clean_db, s)
    c2 = _materialize_candidate(clean_db, s)
    assert c1 == c2
    n = clean_db.execute(
        "SELECT count(*) AS n FROM candidate_skill WHERE candidate_id=%s",
        (c1,)).fetchone()["n"]
    assert n == 2


def test_materialize_job_content_hash_dedup(clean_db, _dataset_file):
    """别名 JD 二次物化 → content_hash 去重复用同一 job。"""
    from skillgap.eval.e2 import _materialize_job
    sample = {"id": "t-012", "jd_text": "z" * 200,
              "jd_source": "别名变体样本（非 job#）"}
    j1 = _materialize_job(clean_db, sample)
    j2 = _materialize_job(clean_db, sample)
    assert j1 == j2
