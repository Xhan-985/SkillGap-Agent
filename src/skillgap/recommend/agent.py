"""Career Planner Agent（Phase 8 任务 4，LangGraph 图 + M9 红线）。

图结构（ADR-006 / 计划 D5）：
  load（确定性：recommend 服务产出 + 候选人画像摘要）
    → generate（LLM 叙事层：解释性文本，禁止改数）
    → verify（数字一致性程序校验）
    →（不一致 → revise（重新 generate，至多 1 次）
    → 仍不一致 / LLM 异常 → 降级模板拼接（永不失数字一致性）
    → 一致 → END

M9 红线：数值路径零 LLM 权限——priority_items / project_suggestions
等结构化结果直接来自 recommend()（规则计算），LLM 输出仅作为 advice
文本（经 check_consistency 校验后附带）。

零真实依赖：gateway 由调用方注入（生产 LLMGateway / 测试 Fake）。
"""
from __future__ import annotations

import operator
import re
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph

from skillgap.recommend.roi import COST_VALUE, render_rationale
from skillgap.recommend.service import recommend

MAX_REVISE = 1          # 验证失败重试次数（D5）
NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _last(old, new):
    return new if new is not None else old


def _add_or_keep(old, new):
    return (old or 0) + (new or 0)


class PlannerState(TypedDict, total=False):
    conn: Any
    gateway: Any
    candidate_id: int
    time_budget_days: int
    market: str
    templates_path: Any
    recommendation: Annotated[dict, operator.or_]
    advice: Annotated[str, _last]
    llm_failed: Annotated[bool, _last]
    bad_nums: Annotated[list, _last]
    revise_count: Annotated[int, _add_or_keep]
    trace: Annotated[list, operator.add]


def check_consistency(advice: str, rec_out: dict) -> list[str]:
    """校验 advice 中出现的数字是否全部可由规则产出解释。

    允许的数字集 = 各 item 的 frequency/potential_gain/gap/sample_size
    及派生（×100 百分比）/ cost_value / est_days / budget / 交集数。
    返回越界数字列表（空 = 通过）。
    """
    allowed: set[float] = set()

    def _allow(v: float) -> None:
        allowed.add(float(v))
        allowed.add(float(round(v)))          # :.0f 四舍五入口径

    for it in rec_out.get("priority_items", []):
        _allow(it["frequency"])
        _allow(it["frequency"] * 100)
        _allow(it["potential_gain"])
        _allow(it["gap"])
        _allow(it["sample_size"])
        _allow(COST_VALUE.get(it["cost"], 0.0))
    for s in rec_out.get("project_suggestions", []):
        _allow(s["est_days"])
        _allow(len(s["matched_skills"]))
    _allow(rec_out["time_budget_days"])
    return [n for n in NUM_RE.findall(advice or "")
            if float(n) not in allowed]


# ---- 节点 ----

def _load(state: PlannerState) -> dict:
    """确定性装载：规则推荐 + 画像摘要（零 LLM）。"""
    rec = recommend(state["conn"], state["candidate_id"],
                    time_budget_days=state["time_budget_days"],
                    market=state.get("market", "china"),
                    templates_path=state.get("templates_path"))
    return {"recommendation": rec, "advice": "", "bad_nums": [],
            "revise_count": 0, "llm_failed": False,
            "trace": [{"step": "load", "ok": True}]}


def _prompt_for(rec: dict) -> str:
    items = rec["priority_items"]
    lines = [
        f"- {i['skill']}：频次 {i['frequency'] * 100:.0f}%、"
        f"缺口 {i['gap']} 星、学习成本{i['cost']}、"
        f"优先分 {i['potential_gain']}" for i in items[:5]]
    projs = [f"- {s['title']}（{s['est_days']} 天，覆盖 "
             f"{'、'.join(s['matched_skills'])}）"
             for s in rec["project_suggestions"][:3]]
    return (
        "你是职业规划助手。基于以下规则引擎产出的结构化数据，"
        "写一段 150 字以内的个性化学习建议（中文）。\n"
        "硬性要求：\n"
        "1. 只能使用数据中出现的数字，禁止计算或编造新数字\n"
        "2. 不要输出 JSON，输出连贯叙事文本\n"
        f"学习预算：{rec['time_budget_days']} 天\n"
        "技能优先级（按 ROI 降序）：\n" + "\n".join(lines) +
        "\n项目建议：\n" + "\n".join(projs))


def _generate(state: PlannerState) -> dict:
    """LLM 叙事层（只读输入，无改数权限）。"""
    step = "revise" if state.get("revise_count") else "generate"
    try:
        resp = state["gateway"].chat(
            [{"role": "user",
              "content": _prompt_for(state["recommendation"])}])
        advice = getattr(resp, "content", None) or ""
        failed = False
    except Exception:                                  # 网络等异常 → 降级
        advice, failed = "", True
    return {"advice": advice, "llm_failed": failed,
            "trace": [{"step": step, "ok": not failed}]}


def _verify(state: PlannerState) -> dict:
    bad = check_consistency(state.get("advice", ""),
                            state["recommendation"])
    return {"bad_nums": bad,
            "trace": [{"step": "verify", "ok": not bad,
                       "bad_nums": bad[:5]}]}


def _revise(state: PlannerState) -> dict:
    return {"revise_count": 1}


def _route(state: PlannerState) -> str:
    if state.get("llm_failed"):
        return "fallback"
    if not state["bad_nums"]:
        return END
    if state["revise_count"] >= MAX_REVISE:
        return "fallback"
    return "revise"


def _fallback_advice(rec: dict) -> str:
    """降级模板：确定性拼接（数字全部来自规则产出）。"""
    items = rec["priority_items"][:3]
    head = (f"基于 {rec['snapshot_ref']['sample_size']} 份真实 JD 的市场"
            if rec.get("snapshot_ref") else "基于真实 JD 市场")
    lines = [f"{head}，你的学习预算 {rec['time_budget_days']} 天。"
             "建议按以下优先级补齐："]
    lines += [f"{i + 1}. {render_rationale(it, rec['time_budget_days'])}"
              for i, it in enumerate(items)]
    if rec["project_suggestions"]:
        s = rec["project_suggestions"][0]
        lines.append(f"项目推荐：{s['title']}（{s['est_days']} 天，"
                     f"覆盖{'、'.join(s['matched_skills'])}）。")
    return "\n".join(lines)


def build_planner_graph() -> StateGraph:
    g = StateGraph(PlannerState)
    g.add_node("load", _load)
    g.add_node("generate", _generate)
    g.add_node("verify", _verify)
    g.add_node("revise", _revise)
    g.set_entry_point("load")
    g.add_edge("load", "generate")
    g.add_edge("generate", "verify")
    g.add_conditional_edges(
        "verify", _route,
        {"revise": "revise", "fallback": END, END: END})
    g.add_edge("revise", "generate")
    return g.compile()


def run_planner(conn, candidate_id: int, time_budget_days: int = 14,
                market: str = "china", templates_path: str | None = None,
                gateway=None) -> dict:
    """完整 Agent 运行入口（CLI agent-plan 调用）。"""
    if gateway is None:
        from skillgap.llm.gateway import LLMGateway
        gateway = LLMGateway()
    graph = build_planner_graph()
    init = {"conn": conn, "candidate_id": candidate_id,
            "time_budget_days": time_budget_days, "market": market,
            "templates_path": templates_path, "gateway": gateway}
    state = graph.invoke(init)

    rec = state["recommendation"]
    if state.get("llm_failed") or state.get("bad_nums"):
        advice, fell_back = _fallback_advice(rec), True
    else:
        advice, fell_back = state["advice"], False
    return {"recommendation": rec, "advice": advice,
            "fallback": fell_back,
            "trace": state["trace"] + [{"step": "end",
                                        "fallback": fell_back}]}
