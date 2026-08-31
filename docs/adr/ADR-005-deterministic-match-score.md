# ADR-005：为什么 LLM 不负责最终 Match Score？

状态：**已接受（Phase 1 冻结，第一设计原则）** ｜ 日期：2026-08-31 ｜ 前身：Phase 0 DESIGN_DECISIONS ADR-002

## Context

需求第二十节红线：禁止"LLM → 你匹配度 78%"直接作为最终结果；Match Score 必须由 Skill Coverage + Skill Importance + Evidence Confidence + Experience Relevance 构成，公式权重有依据，无法证明依据时标记 configurable heuristic 交给 Evaluation 验证。竞品研究：Huntr 的可解释评分已含 LLM 影响的权重——把数值放进确定性层是对其可解释基线的升级差异。评测需求：确定性层可做纯函数单测（单调性检查），LLM 层单独用标注集评测——责任分离使评测可归因。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| **确定性公式计算分数** | 100% 可复现可单测；变更可归因（scoring_version）；评测可分层；LLM 幻觉无法污染决策数字 | 公式设计需要证据支撑；权重初期是启发式（heuristic）需评测校准 |
| 端到端 LLM 生成完整报告（含数字） | 实现快；文本流畅 | 不可评测不可复现；幻觉直接污染决策数字——正是需求要反的"黑盒" |
| LLM 打分 + 规则校验 | 灵活 | 校验层只能拦离谱值，无法保证一致性；顺序颠倒责任 |
| 纯规则无 LLM | 完全确定 | 中文 JD 抽取与解释生成确需 LLM（ADR-009）；且失去解释的自然语言表达力 |

## Decision

**分数 = 纯函数公式（Phase 1 冻结，DATA_MODEL §4）：**

```
Overall = 100 × (0.45×coverage + 0.25×importance_coverage + 0.20×evidence_quality + 0.10×experience_relevance)
conf_factor = 0.5 + 0.5 × confidence    # 证据充分技能贡献更高
```

权重依据：技能覆盖是招聘筛选主体（最大）；must_have 一票否决文化（次之）；证据置信度是本项目差异化（第三）；经验相关性数据最弱（最小）。**全部标记 configurable heuristic，E2 标注集（20-30 对）验证后修订并升 scoring_version。**

LLM 职责边界：只生成解释文本（数值由 UI 从 breakdown 渲染）；解释中数字与 breakdown 程序比对一致性（100% 门禁）。

## Consequences

- 正面：分数可复现（同输入同输出）；能力提升→分数单调上升（可单测）；评分公式公开可辩护；解释错误不污染数据
- 负面：解释文本可能模板感（接受，用证据链弥补）；权重校准依赖标注集建设进度

## Reversibility

撤销成本：**高**（分层是数据流结构，事后融合需重写核心）——故 Phase 1 冻结。
复议触发条件：E2 评测证明确定性排序持续劣于人工预期且 LLM 判序显著更优 → 允许 Phase 8 Agent 内"建议候选生成 + 规则重排"混合（数值仍由公式计算）。
