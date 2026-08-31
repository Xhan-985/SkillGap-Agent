# ADR-007：为什么需要 Evidence？

状态：**已接受（Phase 1 冻结，核心差异化支柱）** ｜ 日期：2026-08-31

## Context

牛客面经研究（MARKET_RESEARCH §3）证明市场存在"死亡追问"文化：面试官逐层验证"你说你会 RAG——切片策略？混合检索怎么做的？rerank 选型？"。求职者被困扰的不是"不知道学什么"，而是**无法证明自己真的会**。需求第十八节：用户说"我会 RAG"，系统不能直接认为 Confidence=100%，应该寻找证据（Resume/Project/README/Code/Dependency）。竞品与开源研究双重排查：无任何竞品做证据化技能画像。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| **Evidence Layer（证据链 + 置信度规则）** | 每个技能结论可回链原文；"声明 vs 证明"可区分（0.45 vs 0.91）；评测可验证（证据可溯率可程序判定） | 需要设计证据类型权重表并维护；简历证据质量依赖输入丰富度 |
| 技能布尔清单（勾选会/不会） | 实现极简 | 无法区分"了解 MCP"与"用 MCP 构建过生产服务"——退化为普通简历工具 |
| LLM 直接给技能置信度 | 表面灵活 | 数字不可复现、不可解释——与 ADR-005 同病 |

## Decision

**建立 Evidence Layer：**

- JD 侧：job_skill.evidence_text（JD 原文支撑片段，字符串定位校验，NOT NULL）
- 用户侧：candidate_evidence（project_detail 1.0 / project_desc 0.6 / bare_claim 0.3 / manual 1.0），confidence = Σ(weight) 归一化 + 次数衰减（纯函数，单测覆盖）
- 系统侧：每个数值输出携带 evidence_ref（频率→JD 集合；分数→breakdown+证据；ROI→公式+快照）
- v2 扩展：GitHub 仓库证据（README/语言/依赖/commit——"声明 vs 代码证明"对比）

## Consequences

- 正面：产品叙事与市场痛点（死亡追问）直接对齐；置信度可辩护（权重表公开）；证据字段是评测的地基
- 负面：证据质量天花板 = 用户输入质量（引导 UI 弥补）；权重表是启发式（经验值公开标注，可迭代）

## Reversibility

撤销成本：**高**（证据字段贯穿全数据模型与 API 契约）——故 Phase 1 冻结。
复议触发条件：无（该决策是差异化根基，回撤等于改变产品定位）。
