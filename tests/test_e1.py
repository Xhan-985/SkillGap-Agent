import pytest

from skillgap.eval.e1 import compute_metrics, run_e1, verdict_for
from skillgap.models import SkillAnnotation
from skillgap.taxonomy.seed import seed_all


def _anns(*pairs):
    return [SkillAnnotation(raw_name=n, importance=im, evidence_text="ev")
            for n, im in pairs]


# ---------- compute_metrics（纯函数，无 DB/LLM） ----------
# 口径（EVALUATION_PLAN §2.2）：micro = 池化全部 (样本,技能) 决策，
# 同名技能跨样本各计一次；样本内同名去重由 run_e1 调 _dedupe_by_name 完成。

def test_metrics_perfect():
    m = compute_metrics(
        extracted=[("RAG", "must_have")], truth=[("RAG", "must_have")])
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["f1"] == 1.0
    assert m["importance_accuracy"] == 1.0


def test_metrics_empty_extraction():
    m = compute_metrics(extracted=[], truth=[("RAG", "must_have")])
    assert m["precision"] == 1.0      # 无误报约定
    assert m["recall"] == 0.0 and m["f1"] == 0.0


def test_metrics_partial_and_importance():
    m = compute_metrics(
        extracted=[("RAG", "must_have"), ("Docker", "must_have")],
        truth=[("RAG", "nice_to_have"), ("Python", "must_have")])
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5
    assert m["importance_accuracy"] == 0.0    # RAG tp 但 importance 错（0/1）


def test_metrics_macro_f1():
    m = compute_metrics(
        extracted=[("RAG", "must_have")],
        truth=[("RAG", "must_have"), ("Python", "must_have"),
               ("Docker", "must_have")])
    assert abs(m["macro_f1"] - round(1 / 3, 4)) < 1e-9


def test_metrics_micro_counts_each_decision():
    """micro 口径：同名跨样本/跨决策各计一次（不做并集去重）。"""
    m = compute_metrics(
        extracted=[("RAG", "must_have"), ("RAG", "must_have")],
        truth=[("RAG", "must_have")])
    assert m["precision"] == 0.5      # 2 个抽取决策，1 个命中
    assert m["recall"] == 1.0
    assert m["f1"] == round(2 * 0.5 * 1.0 / 1.5, 4)


def test_dedupe_by_name_within_sample():
    """样本内同名去重（首个 importance 生效），跨样本不去重。"""
    from skillgap.eval.e1 import _dedupe_by_name
    assert _dedupe_by_name([("RAG", "must_have"), ("RAG", "must_have"),
                            ("Docker", "nice_to_have")]) == [
        ("RAG", "must_have"), ("Docker", "nice_to_have")]


# ---------- 阈值判定（预声明，跑分前冻结——E1 §2.3） ----------

def test_verdict_thresholds():
    assert verdict_for({"f1": 0.9}) == "pass"
    assert verdict_for({"f1": 0.85}) == "pass"
    assert verdict_for({"f1": 0.8}) == "warn"
    assert verdict_for({"f1": 0.75}) == "warn"
    assert verdict_for({"f1": 0.6}) == "block"


def test_evidence_rate_is_hard_requirement():
    assert verdict_for({"f1": 0.9, "evidence_rate": 0.95}) == "block"
    assert verdict_for({"f1": 0.9, "evidence_rate": 1.0}) == "pass"


# ---------- run_e1 端到端（FakeExtractor，验证评测管道） ----------

class FakeExtractor:
    """固定抽取词表内 3 技能；证据取 jd 原文切片（可定位）。"""

    model_name = "fake-model"

    def __init__(self, conn):
        from skillgap.ingest.extract import alias_map_from_db
        self.amap = alias_map_from_db(conn)
        self.n = 0

    def extract(self, jd_text):
        self.n += 1
        return [SkillAnnotation(raw_name="Python", importance="must_have",
                                evidence_text=jd_text[10:30]),
                SkillAnnotation(raw_name="RAG", importance="must_have",
                                evidence_text=jd_text[10:30]),
                SkillAnnotation(raw_name="Docker", importance="nice_to_have",
                                evidence_text=jd_text[10:30])]


def test_run_e1_with_fake_extractor(clean_db):
    from skillgap.eval.seed import seed_eval
    seed_all(clean_db)
    seed_eval(clean_db)
    out = run_e1(clean_db, FakeExtractor(clean_db))
    assert out["sample_size"] == 20
    assert 0.0 <= out["f1"] <= 1.0
    assert out["evidence_rate"] == 1.0
    assert out["prompt_version"] == "fake-v0"
    assert out["verdict"] in ("pass", "warn", "block")
    with clean_db.cursor() as cur:
        cur.execute("SELECT metrics, verdict, eval_type, prompt_version, "
                    "model, sample_size FROM eval_run")
        row = cur.fetchone()
    assert row["eval_type"] == "skill_extraction"
    assert row["sample_size"] == 20
    assert row["prompt_version"] == "fake-v0"
    assert row["model"] == "fake-model"
    assert row["metrics"]["f1"] == out["f1"]


def test_run_e1_extraction_failure_counts_as_miss(clean_db):
    """抽取异常样本：计为空抽取（拉低 recall），不中断评测。"""
    from skillgap.eval.seed import seed_eval
    seed_all(clean_db)
    seed_eval(clean_db)

    class FailingExtractor:
        model_name = "fail"
        calls = 0

        def extract(self, jd_text):
            FailingExtractor.calls += 1
            raise RuntimeError("boom")

    out = run_e1(clean_db, FailingExtractor(),
                 prompt_version="fail-v0")
    assert out["sample_size"] == 20
    assert out["recall"] == 0.0
    assert out["evidence_rate"] == 0.0     # 失败样本证据不可溯
    assert out["verdict"] == "block"
    assert FailingExtractor.calls == 20


def test_run_e1_out_of_taxonomy_skills_excluded_from_pr(clean_db):
    """词表外抽取：不进 P/R 统计（进 new_skill_candidate 属抽取器职责）。"""
    from skillgap.eval.seed import seed_eval
    seed_all(clean_db)
    seed_eval(clean_db)

    class WeirdExtractor:
        model_name = "weird"

        def extract(self, jd_text):
            return [SkillAnnotation(raw_name="不存在的框架XYZ",
                                    importance="must_have",
                                    evidence_text=jd_text[10:30])]

    out = run_e1(clean_db, WeirdExtractor(), prompt_version="weird-v0")
    assert out["precision"] == 1.0    # 词表外不计误报
    assert out["recall"] == 0.0
