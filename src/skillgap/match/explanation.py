"""Match 解释层（Phase 7，API §2.8 / M6 验收）。

双模式（D7）：
- 模板解释（默认）：数字 100% 来自 breakdown/三组计数，零 LLM
- LLM 解释（可选 --llm-explain）：输入=breakdown JSON，Prompt 明令
  "禁止自算数字"；生成后必须过 check_consistency

一致性校验（M6 验收"解释中每个数字与 breakdown 程序比对一致"）：
正则抽取解释文本中全部数字 token，须 ⊆ breakdown 派生数字集
（四维原值/百分比值/总分/三组计数），否则返回不一致清单（空=通过）。
LLM 生成失败 → 降级模板（API §错误表既有约定）。
"""
from __future__ import annotations

import re

from skillgap.match.scoring import breakdown_numbers

_EXPLAIN_PROMPT = (
    "你是招聘匹配分析师。基于下方 JSON 数据写一段 80-150 字的中文匹配"
    "解读：先给总分结论，再点出主要优势（strong）与关键缺口"
    "（missing/weak），最后一句行动建议。\n"
    "铁律：只能直接引用 JSON 中出现的数字（含其百分形式），"
    "严禁自行计算或引入任何新数字。\n\n{payload}"
)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _group_numbers(result: dict) -> set[float]:
    nums = set()
    for key in ("strong_skills", "weak_skills", "missing_skills"):
        nums.add(float(len(result.get(key) or [])))
    return nums


def render_template(result: dict) -> str:
    """确定性模板解释（默认模式，零 LLM）。"""
    b = result["breakdown"]
    ov = result["overall_score"]
    s, w, m = (len(result["strong_skills"]), len(result["weak_skills"]),
               len(result["missing_skills"]))
    s_names = "、".join(result["strong_skills"][:3]) or "无"
    m_names = "、".join(result["missing_skills"][:3]) or "无"
    lines = [
        f"综合匹配 {ov} 分。",
        f"技能覆盖率 {b['coverage'] * 100:.0f}%、核心要求（must_have）覆盖率 "
        f"{b['importance_coverage'] * 100:.0f}%、证据质量 "
        f"{b['evidence_quality'] * 100:.0f}%、经验相关性 "
        f"{b['experience_relevance'] * 100:.0f}%。",
        f"达标技能 {s} 项（{s_names}），证据偏弱 {w} 项，缺失 {m} 项"
        f"（缺口代表：{m_names}）。",
    ]
    if result.get("neutral_flags"):
        lines.append(f"注：{len(result['neutral_flags'])} 个维度走中性值"
                     "（数据不可评估），总分解释力受限于既有信息。")
    return "".join(lines)


def generate_llm_explanation(gateway, result: dict) -> str:
    """LLM 解释（可选）：只组织语言，数字必须来自 breakdown。"""
    import json

    payload = json.dumps(
        {"overall_score": result["overall_score"],
         "breakdown": result["breakdown"],
         "strong_skills": result["strong_skills"],
         "weak_skills": result["weak_skills"],
         "missing_skills": result["missing_skills"]},
        ensure_ascii=False)
    resp = gateway.chat(
        [{"role": "user", "content": _EXPLAIN_PROMPT.format(payload=payload)}])
    return resp.content.strip()


def check_consistency(explanation: str, result: dict) -> list[str]:
    """程序比对：解释中数字 ⊆ breakdown 派生集。返回不一致数字列表。"""
    allowed = breakdown_numbers(result) | _group_numbers(result)
    bad = []
    for tok in _NUMBER_RE.findall(explanation):
        v = float(tok)
        if v in allowed:
            continue
        # 整数形式兼容（如 "0.68" 与 "0.6800"）
        if any(abs(v - a) < 1e-9 for a in allowed):
            continue
        bad.append(tok)
    return bad
