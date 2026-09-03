"""Phase 8 LangGraph Career Planner Agent 单测（Fake LLM，零真实调用）。

验收（计划 D5/D6 + ROADMAP M9）：
- 图结构：load（确定性）→ generate → verify → 条件边（revise 一次
  → 降级模板）
- 回放：同输入同 trace 确定性部分
- verify 拦截自算数字
- LLM 无改数权限：priority_items 逐项等于规则产出
"""
import json

import pytest

from skillgap.recommend.agent import (
    build_planner_graph, check_consistency, run_planner,
)
from tests.test_recommend_service_fixtures import (
    seed_market, write_templates,
)


class FakeLLM:
    """按脚本顺序返回 content 的 gateway 桩。"""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, messages, **kw):
        class R:
            pass
        r = R()
        r.content = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return r


GOOD_REPLY = (
    "建议优先补 MCP：它是当前市场的高频缺口，且学习成本适中。"
    "首选项目 MCP Server 实战（10 天在 14 天预算内）。其次补 Docker。"
)


def test_check_consistency_passes_on_good_reply(clean_db):
    """GOOD_REPLY 数字全部来自 recommend 输出。"""
    cid = seed_market(clean_db)
    from skillgap.recommend.service import recommend
    out = recommend(clean_db, cid, time_budget_days=14,
                    templates_path=_write_templates_and_return())
    bad = check_consistency(GOOD_REPLY, out)
    assert bad == []


def test_check_consistency_catches_alien_numbers():
    """自算数字（频次 90%、预算 99 天）被拦截。"""
    bad_text = "市场需求频次 90%，建议 99 天完成。"
    out = {"priority_items": [
        {"skill": "MCP", "frequency": 0.5, "potential_gain": 2.5,
         "gap": 5, "cost": "low", "sample_size": 32, "type": "genuine",
         "demand_status": "OK", "formula_version": "roi-v1",
         "rationale": "x", "evidence_ref": {"snapshot_id": 1}}],
        "project_suggestions": [
            {"template_id": "t", "title": "t", "matched_skills": ["MCP"],
             "est_days": 10, "source": "s", "rationale": "r",
             "target_skills": ["MCP"], "cost": "mid"}],
        "time_budget_days": 14}
    bad = check_consistency(bad_text, out)
    assert "90" in bad and "99" in bad


def _write_templates_and_return():
    import tempfile
    from pathlib import Path
    return write_templates(Path(tempfile.mkdtemp()))


def test_run_planner_happy_path(clean_db):
    """LLM 叙事通过校验 → advice = LLM 文本 + trace 完整 + 数值未污染。"""
    cid = seed_market(clean_db)
    tp = _write_templates_and_return()
    gw = FakeLLM([GOOD_REPLY])
    out = run_planner(clean_db, cid, time_budget_days=14,
                      templates_path=tp, gateway=gw)
    assert out["fallback"] is False
    assert out["advice"] == GOOD_REPLY
    assert gw.calls == 1
    # trace：至少 load/generate/verify 三步
    steps = [t["step"] for t in out["trace"]]
    assert steps[:3] == ["load", "generate", "verify"]
    # 数值未被 LLM 污染：priority_items 逐项等于规则产出
    from skillgap.recommend.service import recommend
    rule = recommend(clean_db, cid, time_budget_days=14, templates_path=tp)
    assert out["recommendation"]["priority_items"] == rule["priority_items"]


def test_run_planner_verify_fail_then_revise_ok(clean_db):
    """第一次自算数字 → revise 重生成通过（D5 条件边）。"""
    cid = seed_market(clean_db)
    tp = _write_templates_and_return()
    gw = FakeLLM(["频次 90% 完全值得", GOOD_REPLY])
    out = run_planner(clean_db, cid, time_budget_days=14,
                      templates_path=tp, gateway=gw)
    assert out["fallback"] is False
    assert gw.calls == 2                    # revise 重生成一次
    assert [t["step"] for t in out["trace"]] == [
        "load", "generate", "verify", "revise", "verify", "end"]
    assert out["advice"] == GOOD_REPLY


def test_run_planner_verify_fail_twice_falls_back(clean_db):
    """revise 仍不过 → 降级模板（不抛错，advice 为模板拼接）。"""
    cid = seed_market(clean_db)
    tp = _write_templates_and_return()
    gw = FakeLLM(["频次 90% 假数据", "又是 90%"])
    out = run_planner(clean_db, cid, time_budget_days=14,
                      templates_path=tp, gateway=gw)
    assert out["fallback"] is True
    assert gw.calls == 2                    # 只试两次
    # 降级 advice 数字仍一致
    assert check_consistency(out["advice"], out["recommendation"]) == []


def test_run_planner_llm_failure_falls_back(clean_db):
    """LLM 网络异常 → 降级模板。"""

    class FailingGW:
        def chat(self, *a, **kw):
            raise RuntimeError("网络故障")

    cid = seed_market(clean_db)
    tp = _write_templates_and_return()
    out = run_planner(clean_db, cid, time_budget_days=14,
                      templates_path=tp, gateway=FailingGW())
    assert out["fallback"] is True
    assert check_consistency(out["advice"], out["recommendation"]) == []


def test_build_planner_graph_structure():
    """图结构冻结：load → generate → verify →（revise→verify | END）。"""
    g = build_planner_graph()
    assert set(g.nodes) == {"load", "generate", "verify", "revise",
                            "__start__"}


def test_run_planner_candidate_not_found(clean_db):
    seed_market(clean_db)
    with pytest.raises(Exception):
        run_planner(clean_db, 999, gateway=FakeLLM([GOOD_REPLY]))
