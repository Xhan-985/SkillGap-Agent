# ADR-009：技能抽取为什么用 LLM Structured Output + Taxonomy 归一？

状态：**已接受（Phase 1 冻结，Phase 3 实现）** ｜ 日期：2026-08-31 ｜ 前身：Phase 0 DESIGN_DECISIONS ADR-003（需求"至少 8 个 ADR"之外保留的 Phase 0 决策）

## Context

需求第十七节：Skill Taxonomy 需支持 Category/Alias/Synonym/Parent/Related Skill（"Postgres/PostgreSQL/PG → PostgreSQL"），且**不能只靠字符串匹配**，需要"LLM + Rule + Validation"。中文 JD 现实：技能表述变体多（"检索增强生成/RAG"、"熟悉 LangChain 框架"、"vLLM/sglang/lmdeploy"），规则匹配召回低。开源验证：ResumeRadar（NER+白名单）、JobBot（ESCO 锚点）证明"模型抽取 + 词表归一"是正解。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| **LLM Structured Output + alias/ESCO 归一 + 校验** | 抽取质量可评测（E1 标注集 P/R/F1）；证据片段强制输出（Evidence Layer 数据来源）；换模型只影响抽取层 | LLM 成本与延迟（content_hash 缓存缓解）；质量依赖 Prompt 迭代（回归历史管理） |
| 纯关键词/正则词典 | 零成本零延迟 | 被需求明令禁止；中文变体覆盖差；无证据输出 |
| 微调专用 NER 模型 | 推理便宜 | 无足够标注数据（几百 JD 养不起模型）；维护成本错配单人项目 |
| 嵌入相似度匹配技能库 | 归一化辅助好（"LangGraph"≈"LangGraph.js"） | 抽取本身仍需模型；单独用作抽取召回不稳 |

## Decision

**LLM Structured Output（Pydantic Schema：技能名/重要度/程度词/证据片段）→ alias 表 + ESCO 锚点归一化 → 校验（证据片段必须在原文可定位，不可定位即失败）→ 入库。** 词表外新词进 new_skill_candidate 表人工周级裁决（不静默入表、不丢弃）。嵌入相似度仅作归一排序建议。失败重试 ≤2 次后明示失败。

## Consequences

- 正面：中文抽取召回可保障；归一正确性由 E1 对抗用例守门（LangChain vs LangChain.js 应同归一）；词表可持续生长且受控
- 负面：词表维护是长期成本（new_skill_candidate 队列）

## Reversibility

撤销成本：**低-中**（抽取层独立模块，可换实现而 Schema 不变）。
复议触发条件：E1 F1 持续 <0.75 且迭代 3 轮无改善 → 缩小词表（MVP.md §7 止损线）。
