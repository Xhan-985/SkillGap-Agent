"""E3 LLM-as-judge 测试（rubric-v1：解析/评分/失败跳过/verdict 隔离）。"""
from __future__ import annotations

import json

import pytest

from skillgap.eval.judge import (
    RUBRIC_VERSION, judge_recommendation, parse_judge_response,
)
from skillgap.llm.provider import LLMResponse


class FakeJudgeProvider:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.calls = 0

    def chat(self, messages, response_json=False):
        self.calls += 1
        if self.error:
            raise self.error
        return LLMResponse(content=self.content)


# ---------- 解析（容错） ----------

def test_parse_plain_json():
    out = parse_judge_response('{"score": 5, "reason": "完全引用"}')
    assert out == {"score": 5, "reason": "完全引用"}


def test_parse_json_with_prose():
    out = parse_judge_response(
        "评审结论如下：\n{\"score\": 3, \"reason\": \"口径含糊\"}\n以上。")
    assert out["score"] == 3


def test_parse_regex_fallback():
    out = parse_judge_response("评分：score: 4，理由略。")
    assert out["score"] == 4


def test_parse_garbage_raises():
    with pytest.raises(ValueError):
        parse_judge_response("完全无法解析的输出")


def test_parse_out_of_range_score_raises():
    with pytest.raises(ValueError):
        parse_judge_response('{"score": 9, "reason": "x"}')


# ---------- judge_recommendation ----------

def test_judge_recommendation_ok():
    p = FakeJudgeProvider(content='{"score": 5, "reason": "数字全引用"}')
    out = judge_recommendation(p, {"priority_items": [], "time_budget_days": 14})
    assert out["score"] == 5
    assert out["rubric_version"] == RUBRIC_VERSION == "rubric-v1"
    assert p.calls == 1


# ---------- run_e3 集成（FakeLLM 全链路，见 test_eval_e3 的 run 依赖） ----------

def _fake_judge_provider(score=5, error=None):
    return FakeJudgeProvider(
        content=json.dumps({"score": score, "reason": "ok"}, ensure_ascii=False),
        error=error)


@pytest.fixture()
def e3_env(clean_db, tmp_path):
    """最小可跑分环境（复用 runner 测试的数据集与市场种子）。"""
    import json

    from skillgap.eval.e3 import seed_eval3
    from tests.test_eval_e3_runner import _DATASET
    from tests.test_recommend_service_fixtures import seed_market

    seed_market(clean_db)
    path = tmp_path / "e3_test.json"
    path.write_text(json.dumps(_DATASET, ensure_ascii=False),
                    encoding="utf-8")
    seed_eval3(clean_db, str(path))
    return clean_db


def test_run_e3_with_judge_appends_warn_metrics(e3_env):
    from skillgap.eval.e3 import run_e3
    base = run_e3(e3_env, dataset_version="e3-test")
    judged = run_e3(e3_env, dataset_version="e3-test",
                   judge_provider=_fake_judge_provider(4))
    # verdict 隔离（红线：judge 不参与 Block/pass 判定）
    assert judged["verdict"] == base["verdict"]
    assert judged["ndcg@5"] == base["ndcg@5"]
    j = judged["judge"]
    assert j["mean"] == 4.0
    assert j["n_judged"] == base["n_cases"]
    assert j["rubric_version"] == "rubric-v1"
    assert len(j["judged_cases"]) == base["n_cases"]


def test_run_e3_judge_failure_skips_without_breaking(e3_env):
    from skillgap.eval.e3 import run_e3
    out = run_e3(
        e3_env, dataset_version="e3-test",
        judge_provider=_fake_judge_provider(error=RuntimeError("网络炸了")))
    assert out["judge"] == {"mean": None, "n_judged": 0,
                            "rubric_version": "rubric-v1",
                            "judged_cases": []}
    assert out["verdict"]  # 主体跑分不受影响
