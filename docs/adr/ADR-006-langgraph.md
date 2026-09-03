# ADR-006：为什么/为什么不使用 LangGraph？

状态：**已接受并复议（2026-09-04 Phase 8 落地：单 Career Planner Agent + LangGraph，边界=解释层旁路，数值路径零 LLM 权限；结论见文末复议记录）** ｜ 日期：2026-08-31 ｜ 前身：Phase 0 DESIGN_DECISIONS ADR-005

## Context

需求第二十三节：不要为了简历强行 Multi-Agent；只有任务确实需要多步骤决策、状态管理、工具调用、循环、动态路径时才使用 Agent / LangGraph；如果普通 Workflow 更合理就用 Workflow；必须记录架构取舍。

v1（M1-M11）的任务链：抽取→归一→统计→打分→排序→解释，全部是**确定性流程**——每一步的输入输出可预先定义，没有需要动态决策的分叉。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| **v1 纯 Workflow（规则+排序），Phase 8 单 Agent** | v1 全链路可测试可评测；引入 Agent 时决策依据已冻结（Agent 拿不到改数字权限）；面试叙事完整（"先证明规则够用"） | v1 用户无法自然语言追问（用解释面板+证据链接弥补） |
| v1 即引入 LangGraph | 展示编排能力 | 无决策需求 → 纯负资产：把可解释确定性计算包进状态机，增加调试面与 LLM 成本 |
| 五 Agent 流水线（Market/Skill/Candidate/Gap/Planner） | 看起来"架构高级" | 前四段是确定性计算，Agent 化把白盒变黑盒链——与 ADR-005 直接冲突；延迟成本 ×5；评测无法归因 |
| 多 Agent 自治协作（CrewAI/AutoGen 风格） | 无收益场景 | 行为不可复现；单人项目无法调试多 Agent 边界 |
| 自写状态机（不用 LangGraph） | 零依赖 | Phase 8 真需要时是重复造轮子（检查点/回放已有成熟实现） |

## Decision

**v1（Phase 1-7）：无 Agent——普通 Workflow。Phase 8：引入单一 Career Planner Agent（LangGraph），输入 = 冻结的确定性计算快照（只读），输出 = 建议与解释，带 Trace/回放。** 架构在 Recommend Context 接口层预留（输入为只读快照），引入时无重构。

## Consequences

- 正面：v1 零编排复杂度；Agent 引入时机由证据决定（用户开放问题需求占比、规则覆盖不足的实测）
- 负面：LangGraph 技能展示延后到 Phase 8（接受——用户已有 LangGraph 经验，价值在"用对地方"而非"用了"）

## Reversibility

撤销成本：**中**（Agent 是旁路编排层，撤除不影响确定性核心；深度集成 UI 则需返工展示层）。
复议触发条件：① Phase 8 评测显示规则推荐质量已达标且追问需求弱 → 延后；② 规则无法覆盖的用户场景 >30% → 提前。

## 复议记录（2026-09-04，Phase 8 落地时）

**结论：引入成立，但边界严格。**

- 规则推荐（roi-v1）先行独立验收：任务 1-3 零 Agent 可用（E3 基线 pass 证明规则达标），Agent 不在数值路径上
- 引入的正当场景 = 解释个性化（"为什么推荐它而非它"的叙事），这是规则模板覆盖不了的
- 落地形态：4 节点单图 load（确定性）→ generate（叙事）→ verify（数字程序比对）→（revise 一次 → 仍败 → 降级模板），复杂度与问题规模匹配
- 真实 e2e 证据：DeepSeek 两次生成无来源数字（"20 个评测用例"）均被 verify 拦截 → 降级模板输出（fallback=true，trace 六步留档）——"Agent 拿不到改数字的权限"在真实 LLM 流量下工作
- 版本锁定 langgraph ≥0.3,<0.4（Reversibility：撤除成本已验证——图仅 4 节点，回退手写状态机成本低）
