# ARCHITECTURE —— 技术架构（Phase 1 冻结版）

> SkillGap Agent ｜ Phase 1 交付物 ｜ 本版在 Phase 0 基础上新增数据采集上下文（Adzuna ingest + 用户贡献通道），API 契约冻结至 API.md，ADR 迁移至 docs/adr/（变更记录见 DECISION_LOG.md）
> 架构一句话：**模块化单体（Modular Monolith）+ 三层智能分离（Deterministic / LLM / Evidence），Agent 只在 Phase 8 以单 Agent + Workflow 形式引入。**

---

## 1. 架构决策摘要

| 项 | 内容 |
|---|---|
| **目标** | 完整跑通"数据采集→JD→频率→画像→缺口→匹配→ROI→建议"闭环；每个输出可追溯；评测可复现；clone 即可运行 |
| **非目标** | 高并发生产部署、多租户 SaaS、实时数据管道、微服务拆分 |
| **约束** | 单人开发 + 简历级项目周期；LLM API 成本可控；数据来源合法合规（禁止爬虫，ADR-001）；中国/全球市场分离 |
| **决策状态** | **Phase 1 冻结**（docs/adr/ADR-001~009） |

**核心架构裁决**：单体优先（Monolith-first），内部按有界上下文划分模块；不为展示"分布式/多 Agent"支付复杂度溢价。每个微服务化/多 Agent 化的提议必须指出具体命名收益，否则默认拒绝（需求第二十三节要求记录取舍，见 §6）。

---

## 2. 总体架构

```
┌────────────────────────────────────────────────────────────────┐
│                        Dashboard (展示层)                        │
│      画像 │ 雷达 │ 热门技能 │ 缺口 │ ROI │ 匹配解释 │ 目标岗位      │
└───────────────────────────────┬────────────────────────────────┘
                                │ HTTP/JSON
┌───────────────────────────────▼────────────────────────────────┐
│                    API Layer —— FastAPI                          │
│         /jd /profile /market /match /gap /recommend /eval        │
├────────────────────────────────────────────────────────────────┤
│                          应用核心（模块化单体）                    │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Ingestion     │  │ JD Context    │  │ Candidate            │   │
│  │ (ingest模块)  │  │ (jd模块)      │  │ Context (profile模块)│   │
│  │ Adzuna拉取     │  │ 解析/抽取/归一 │  │ 简历证据/置信度        │   │
│  │ 贡献通道/导入   │  │              │  │                     │   │
│  │ PII/去重/质检  │  └──────┬───────┘  └──────────┬───────────┘   │
│  └──────┬───────┘           │                     │               │
│         │         ┌─────────▼─────────────────────▼───────────┐   │
│         │         │              Market Context (market模块)   │   │
│         └────────►│ 频率统计/切片(SQL)/快照（分市场 China/Global）│   │
│                   └──────────────────┬──────────────────────┘   │
│                                      │                            │
│  ┌───────────────────────────────────▼───────────────────────┐   │
│  │              Matching Context (match模块)                   │   │
│  │   确定性加权评分 │ Skill Gap 计算 │ ROI 计算(公式)           │   │
│  └──────────────────────────┬────────────────────────────────┘   │
│                             │                                    │
│  ┌──────────────────────────▼────────────────────────────────┐   │
│  │           Recommend Context (recommend模块)                │   │
│  │   v1: 规则+排序  │  Phase 8: Career Planner Agent(LangGraph)│   │
│  │   v1: 直接引用JD记录  │  Phase 8+: RAG 知识问答(pgvector)     │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────┐  ┌──────────────────────────────────┐  │
│  │ LLM Gateway        │  │ Evidence Layer                    │  │
│  │ Provider抽象        │  │ 证据存储/置信度规则/溯源查询         │  │
│  │ Structured Output  │  │ (JD原文片段↔技能↔简历证据↔快照)     │  │
│  │ 校验+重试           │  │                                  │  │
│  └─────────────────────┘  └──────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  Data Layer: PostgreSQL(+pgvector预留) + Redis(缓存)         │  │
│  │  Ingestion管道(DATA_PIPELINE S1-S10) + 评测集管理 + 质量指标    │  │
│  └────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

**外部数据源（经 Ingestion Context 进入，全部确定性代码，无爬虫）**：Adzuna 公开 API（Tier A，Global）｜公司官方招聘页人工摘录（Tier A）｜用户 opt-in 匿名贡献（Tier B，China 主通道）｜CSV/JSON 导入（Tier C）。管道分步规格见 DATA_PIPELINE.md。

**三层智能分离**（需求第十四节要求的架构化表达）：

| 层 | 职责 | 技术手段 | 禁止事项 |
|---|---|---|---|
| **Deterministic Layer** | 频率统计、匹配分数、Gap 计算、ROI 数值 | SQL / Python 纯函数 | LLM 参与 |
| **LLM Layer** | 技能抽取（Structured Output）、解释生成、简历证据识别 | LLM API + Schema 校验 | 修改任何数值 |
| **Evidence Layer** | 溯源查询、证据存储、置信度规则 | 数据库 + 规则引擎 | 无证据的断言 |

---

## 3. 系统数据流与信任边界

```
外部输入（不可信边界）              系统内部（可信）
─────────────────              ─────────────────
用户粘贴 JD ──────┐
用户上传简历 ──────┼──→ 输入校验/清洗 → LLM 抽取(Schema校验/失败重试)
CSV/JSON 导入 ────┤                    → Taxonomy 归一化(白名单+别名表)
                  │                    → 入库(含 content_hash 去重)
                  ▼                        ↓
                                        统计/计算(SQL+纯函数) ← 全部确定性
                                            ↓
LLM API（外部依赖）→ 只用于抽取/解释，输出必过校验 → 展示层
                                            ↓
用户反馈 ────────────────→ 评测集/回归历史（回流）
```

**信任边界规则**：
1. 用户粘贴的 JD/简历文本是**不可信输入**：入库前清洗、限长、转义；LLM 抽取结果必须通过 Pydantic Schema 校验，校验失败重试有限次数后明示失败
2. LLM API 是**外部运行时依赖**：超时/失败必须有降级路径（JD 分析失败→明确报错，不静默编造）；Provider 可替换（§5）
3. 输出给用户的每个数字在**可信侧**生成（确定性层）

---

## 4. 技术栈（每项回答"为什么需要"）

| 技术 | 为什么需要 | 不用的后果 | 深度决策 |
|---|---|---|---|
| Python 3.11+ | 数据处理(Pandas) + LLM 生态 + 用户技术栈匹配 | 双语言维护成本 | ADR-003 |
| **FastAPI** | 异步 API + Pydantic 原生 Schema 校验（Structured Output 的校验层直接复用） | 校验逻辑两套实现 | ADR-003 |
| **PostgreSQL** | 结构化 JD/技能关系数据 + 关系查询（频率统计全是 SQL，含 market 分区约束） | 频率统计退化成内存计算，无法审计 | ADR-003 |
| pgvector（表结构预留） | Phase 8 RAG 候选场景；**不提前建索引** | 届时需迁移表结构 | ADR-004 |
| **Redis** | LLM 抽取结果缓存（同 JD content_hash 命中免重抽，成本控制）+ 评测结果缓存 | LLM 成本随重复分析线性增长 | ADR-003 |
| LLM API（OpenAI-compatible） | 抽取/解释的唯一智能来源 | 无核心功能 | ADR-005/009 |
| Structured Output（JSON Schema） | 抽取结果可校验、可入库、可评测 | 自由文本无法进数据库 | ADR-009 |
| **LangGraph**（Phase 8 起） | Career Planner Agent 的确定性编排（状态机 + 检查点），只用于真正需要决策的环节 | v1 不需要；直接手写规则更可解释 | ADR-006 |
| Pandas | 数据集导入清洗、评测集分析 | 手写循环 | ADR-003 |
| Docker Compose | clone→run 一条命令（MVP 成功标准） | 环境不可复现 | ADR-003 |
| pytest | 纯函数层（评分/ROI/置信度/PII 规则）单测 + 评测集回归 | 确定性层无质量门 | ADR-005 |
| GitHub Actions | CI：测试 + 评测跑分 + 统计模块零 LLM 依赖静态检查 | 回归无守门 | ADR-005/008 |

**技术栈纪律**：上表之外引入任何新依赖，必须在 DESIGN_DECISIONS.md 补 ADR 并回答"为什么需要"（需求第一节"不要为了技术而技术"）。

---

## 5. Provider Abstraction（LLM 网关，需求第二十九节）

```
LLMProvider (抽象接口)
 ├── generate(prompt) -> text                          # 解释生成（S12）
 ├── generate_structured(prompt, schema) -> ValidatedModel  # 技能抽取/简历证据识别（S8）——域方法
 │                                                      #   extract_skills / extract_resume_evidence
 │                                                      #   是它的两个特化封装
 └── embed(texts) -> vectors                           # Phase 8 RAG 预留（v1 抛 NotImplementedError，
                                                        #   与 pgvector 表预留同步，ADR-004）
实现（第一版仅一个）：
 └── OpenAICompatibleProvider(base_url, api_key, model)
      └── 兼容 DeepSeek / Qwen / GLM 等 OpenAI-compatible 端点
```

- **第一版只实现一个 Provider**（需求第二十九节红线）；切换 Provider = 改配置
- 业务层**不直接依赖任何厂商 SDK**，只依赖 LLMProvider 接口（需求第二十九节）
- 网关职责：Schema 校验、失败重试（有限次）、结果缓存键（content_hash + model + prompt_version）、成本/延迟记录（为 Evaluation 与成本观测留数据）
- **明确不做**：多 Provider 路由、自动降级切换、并发对比（均为 YAGNI）

---

## 6. Agent 架构取舍（需求第二十三节要求记录）

### 裁决：v1 = 无 Agent（规则 + 排序）；Phase 8 = **单 Agent + LangGraph Workflow**

| 方案 | 优点 | 缺点 | 判决 |
|---|---|---|---|
| A. 纯规则/流水线（v1） | 完全可解释、可测试、可评测；无 LLM 成本 | 无法处理开放性输入（如用户问"我该转 Go 还是继续 Python"） | **MVP 采用**——v1 决策链路（归一化/统计/Gap/匹配分/ROI）全部确定性；LLM 仅存在于抽取（M1-M5 管道内，S8）与解释生成（M6/M9 可选，S12）的受控节点（2026-08-31 评审 H4 修正） |
| B. 单 Agent + LangGraph（Phase 8） | 状态机可回放（Trace/检查点）；复杂决策路径可编排；与用户已掌握技术栈匹配 | 引入 LLM 不确定性到决策层 | **Phase 8 采用**——限定于"个性化优先级决策 + 开放问题解答" |
| C. 五 Agent 流水线（Market/Skill/Candidate/Career Planner 分拆） | 展示 Multi-Agent 能力 | 每步 Agent 化会把可解释的确定性计算变成黑盒链——**与项目第一设计原则直接冲突**；延迟与成本 ×5 | **否决**（除非 Phase 8 评测证明单 Agent 无法承载） |

**否决理由记录**（面试必问）：规划文档的"Market→Skill→Candidate→Gap→Planner"五段图不是五个 Agent 的规格，而是**一条数据流水线的五个阶段**——前四段是确定性计算，只有 Planner 段需要推理。为了展示 Multi-Agent 而拆分，违反"Agent 只用于真正需要推理和决策的地方"。

### RAG 使用定位（需求第二十四节）

- v1 不需要 RAG：解释 = 直接查库引用 JD 记录（数据已在关系库）
- Phase 8+ 引入场景：用户开放性问题（"为什么推荐 MCP 而不是 vLLM"）→ 检索 JD 原文/频率/口径作为上下文 → 回答必须带引用
- pgvector 表结构 Phase 2 预留，索引按需创建

---

## 7. 有界上下文图（Bounded Context Map）

| 上下文 | 职责 | 语言/模型 | 上游 | 下游 | 与邻居的关系 |
|---|---|---|---|---|---|
| **Ingestion Context** | 数据源接入（Adzuna/贡献/导入）、PII 脱敏、去重、质检、来源登记 | RawRecord/PIIRule/QualityVerdict | 外部数据源（不可信边界） | JD Context、Market | **防腐层**：把外部源载荷翻译成内部 Job 模型；Tier 分级在此执行（ADR-002） |
| **JD Context** | JD 解析、技能抽取、归一化 | Job/SkillExtraction/Taxonomy | Ingestion Context | Market、Matching | 对 Market 是**客户/供应商**（供给结构化 JobSkill）；对 LLM Gateway 是**防腐层**（外部模型输出→内部 Schema） |
| **Market Context** | 频率统计、切片、快照 | MarketSnapshot/Frequency | JD Context | Matching、Dashboard | 对 JD 是**顺从**（直接消费其模型，不做二次翻译） |
| **Candidate Context** | 简历解析、证据化画像、置信度 | Candidate/Evidence/Confidence | 用户输入 | Matching、Recommend | 与 JD Context **各自独立**（技能模型共享 Taxonomy 这一**共享内核**——唯一共享数据结构） |
| **Matching Context** | 匹配评分、Gap、ROI | MatchResult/GapScore | JD + Candidate + Market | Recommend | **防腐层**：把三个上游模型翻译成统一打分输入 |
| **Recommend Context** | 优先级建议、项目推荐、（Phase 8）Agent | Recommendation/Priority | Matching + Market | Dashboard | 对 Matching 是**顺从**；LLM 解释输入为只读快照 |
| **Evaluation Context** | 标注集、评测执行、回归历史 | EvaluationSample/Metric | 全部（只读） | CI/报告 | **独立**：只读消费各上下文输出，禁止反向影响 |

**共享内核警告**：Skill Taxonomy 是唯一允许跨上下文共享的数据结构，其变更需同步评测集（变更责任：用户 + CI 检查——评测集与词表一致性测试）。

---

## 8. API 概览（契约冻结于 API.md）

端点全集（16 个）与请求/响应/错误规格见 **API.md**。结构概览：

```
POST /api/jd/analyze ｜ /api/jd/contribute ｜ /api/jd/import ｜ /api/ingest/adzuna   # 输入侧
POST /api/resumes/analyze ｜ GET/DELETE /api/candidates/{id}…                          # 画像侧
POST /api/match ｜ GET /api/candidates/{id}/gaps ｜ POST /api/recommendations          # 决策侧
GET  /api/market/skills ｜ /api/market/skills/{id}/evidence                             # 市场侧
GET  /api/quality/report ｜ /api/eval/results ｜ /api/health                            # 治理侧
```

契约原则：所有数值字段带 `evidence_ref`（指向 JD/证据记录 ID）；错误响应区分"抽取失败"与"样本不足"，不静默。

---

## 9. 适应度函数（架构不变量的可测试检查）

| 不变量 | 度量 | 阈值/规则 | 检查方式 |
|---|---|---|---|
| 确定性层无 LLM | 统计/评分/ROI 代码路径引用 LLM 客户端 | 0 处（静态检查） | CI：import 依赖检查 |
| 数值可溯源 | API 返回的每个数值含 evidence_ref | 100% | 契约测试 |
| LLM 输出必过校验 | 抽取结果 Schema 校验 | 校验失败即拒绝入库 | 单测 + 集成测试 |
| 数据透明 | JD 记录无 source/collected_at/content_hash | 0 条违规 | DB 约束 + 测试 |
| 评测可复现 | 同版本评测集重跑结果差异 | 0（确定性部分）/ 方差报告（LLM 部分） | CI 评测任务 |
| 抽取缓存正确 | content_hash 命中返回与首次一致 | 100% | 单测 |
| 样本量守门 | 统计输出在 N < 阈值时返回"样本不足" | 100% | 单测（边界用例） |

---

## 10. 部署拓扑（MVP）

```
Docker Compose：
  web(FastAPI+Dashboard) ──→ postgres(pgvector镜像，索引按需)
                        ──→ redis(缓存)
                        ──→ LLM API(外部，经 LLM Gateway)
  ci(GitHub Actions)：test → eval(评测集回归) → lint → docs 检查
```

不做：K8s、多环境、CD 自动发布（简历项目无此收益）。
