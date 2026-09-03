"""E3 LLM-as-judge（EVALUATION_PLAN §4.1 解释合理性 / §4.2 控制）。

定位（红线）：**Warn 级参考信号，不作 Block 依据**——数值正确性才是硬门。
控制措施：
- rubric-v1 冻结版本化（变更须升版本 + 复核 10 条锚定样本）
- judge 模型与被测生成模型不同源（deepseek-reasoner vs deepseek-chat，
  同厂商不同模型——C2 已知限制，如实记录）
- 单条失败/解析异常跳过不中断（计划风险条款），报告明示 judge 覆盖率
"""
from __future__ import annotations

import json
import re

RUBRIC_VERSION = "rubric-v1"

RUBRIC_PROMPT = """你是推荐系统质量评审（rubric-v1）。给定规则引擎产出的学习建议数据，按量表评分：

5 = 解释完全引用给定数字（频次/缺口/成本/优先分），无任何编造，排序符合 需求×缺口÷成本 逻辑，预算内项目建议匹配
4 = 个别措辞含糊但无事实错误
3 = 有轻微不准（如四舍五入口径不一致）但不影响决策
2 = 出现给定数据之外的数字或事实性断言
1 = 严重幻觉（编造频次/样本量/技能）或建议与数据矛盾

评审对象数据：
{payload}

只输出 JSON：{{"score": <1-5 整数>, "reason": "<30字以内理由>"}}"""

_SCORE_RE = re.compile(r'"?score"?\s*[:：]\s*([1-5])')


def _payload_for(rec_out: dict) -> str:
    """推荐结果 → judge 输入材料（前 5 优先项 + 前 3 项目建议）。"""
    lines = [
        f"- {i['skill']}：频次 {i['frequency']}、缺口 {i['gap']} 星、"
        f"成本 {i['cost']}、优先分 {i['potential_gain']}、"
        f"解释：{i.get('rationale', '')}"
        for i in rec_out.get("priority_items", [])[:5]]
    projs = [
        f"- {s['title']}（{s['est_days']} 天，覆盖 "
        f"{'、'.join(s['matched_skills'])}）"
        for s in rec_out.get("project_suggestions", [])[:3]]
    return (f"学习预算：{rec_out.get('time_budget_days')} 天\n"
            "技能优先级（按 ROI 降序）：\n" + "\n".join(lines) +
            ("\n项目建议：\n" + "\n".join(projs) if projs else "\n项目建议：无"))


def parse_judge_response(text: str) -> dict:
    """解析 judge 输出（容错：JSON 块 → 正则 score 兜底）。"""
    try:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            d = json.loads(m.group(0))
            score = int(d["score"])
            if 1 <= score <= 5:
                return {"score": score, "reason": str(d.get("reason", ""))}
    except (ValueError, KeyError, TypeError):
        pass
    m = _SCORE_RE.search(text or "")
    if m:
        return {"score": int(m.group(1)), "reason": ""}
    raise ValueError(f"judge 输出无法解析: {(text or '')[:100]}")


def judge_recommendation(provider, rec_out: dict) -> dict:
    """单条推荐 → {score, reason, rubric_version}。

    provider 为 OpenAICompatibleProvider（temperature=None 构造，
    reasoner 不支持 temperature）。
    """
    resp = provider.chat([{"role": "user",
                           "content": RUBRIC_PROMPT.format(
                               payload=_payload_for(rec_out))}])
    out = parse_judge_response(resp.content)
    out["rubric_version"] = RUBRIC_VERSION
    return out
