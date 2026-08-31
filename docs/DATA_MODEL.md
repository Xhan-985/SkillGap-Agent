# DATA_MODEL —— 数据模型设计（Phase 1 冻结版）

> SkillGap Agent ｜ Phase 1 交付物 ｜ 本版替代 Phase 0 版本（变更记录见 DECISION_LOG.md D-2026-08-31-02）
> 原则：**只设计承载闭环与评测所需的表，不为显得复杂而加表。每张表必须回答"为什么需要"。**

---

## 1. ER 图

```
┌──────────────┐
│ data_source  │（来源字典：Tier/许可/归属信息）
└──────┬───────┘
       │1
       ▼N
┌──────────┐         ┌──────────────┐         ┌──────────────┐
│ Company  │1───────N│    Job       │N───────N│    Skill     │
└──────────┘         └──────┬───────┘         └──────┬───────┘
                            │N                       │1
                     ┌──────▼───────┐         ┌──────▼────────┐
                     │  JobSkill   │         │ SkillAlias    │
                     │ 要求+证据    │         │ +新词候选表    │
                     └──────────────┘         └───────────────┘
                            ▲N(评测中引用)
┌──────────┐ 1───────N ┌────┴─────────┐
│Candidate │           │EvaluationSample│
└────┬─────┘           └──────────────┘
     │1
┌────▼──────────┐
│CandidateSkill │──N──── Skill（复用同一张表）
└────┬──────────┘
     │1
┌────▼─────────────┐     ┌──────────────┐     ┌────────────────┐
│CandidateEvidence │     │MatchResult   │     │MarketSnapshot   │
│ 证据+置信度        │     │(Candidate×Job)│     │(分市场统计快照)   │
└──────────────────┘     └──────┬───────┘     └────────────────┘
                                │1
                         ┌──────▼────────┐    ┌────────────────┐
                         │Recommendation │    │ DeletionCode   │
                         │ 优先级+依据    │    │ (贡献删除凭证)  │
                         └───────────────┘    └────────────────┘
```

**关系要点**：`Skill` 是核心共享内核（JD 侧要求与用户侧能力指向同一 skill_id，匹配与 Gap 才可计算）；`data_source` 把许可/归属信息收敛到字典表，job 行只存引用；`skill_relation`（Parent/Related，需求第十七节）支撑 M7 transferable 判定（§4.4）。

---

## 2. 实体定义

### 2.1 data_source（来源字典）—— *为什么需要：来源九字段中 name/license/attribution 是源级属性，收敛字典表避免每行冗余，且 Tier 分级挂在此表*

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| source_type | enum | `public_api` / `public_job_page` / `user_submitted` / `csv_import` / `dataset_builtin` |
| source_name | text(唯一) | `adzuna` / `company_career_page` / `community` … |
| **trust_tier** | enum | `tier_a` / `tier_b` / `tier_c`（ADR-002 Trust Model） |
| **license_or_usage_note** | text | 使用条款摘要（Adzuna attribution 要求等，DATA_GOVERNANCE §6） |
| attribution_html | text | 展示层归属标识（如 "Jobs by Adzuna" 链接） |
| covers_market | enum | `china` / `global` / `both` |
| terms_checked_at | date | 条款核查日期（过期须重查） |

### 2.2 job（岗位）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| title | text | 岗位标题 |
| job_category | enum | 岗位类别词表 v1（§5.1） |
| company_id | FK → company | 可空（匿名 JD） |
| city / **country** / **region** | text | 可空；海外数据来自 API 结构化字段 |
| **market** | enum | **`china` / `global`（统计分市场硬约束，ADR-002）** |
| **language** | enum | `zh` / `en`（规范化步骤判定） |
| salary_min / salary_max / salary_currency | int/text | 可空（中国：月·元；海外：年·原币） |
| raw_text | text | 清洗后 JD 原文（贡献数据为**脱敏后**文本） |
| **status** | enum | `active` / `quarantine` / `extraction_failed` / `rejected`（只有 active 进统计） |
| **source_id** | FK → data_source | |
| source_type | enum | 冗余自字典表（高频查询/约束校验） |
| **source_url** | text | public_job_page 必填（CHECK） |
| **collected_at** | timestamp | 采集/导入时间 |
| **submitted_at** | timestamp | 用户提交时间（API 源为空） |
| **content_hash** | text(唯一索引) | 规范化文本哈希，导入去重 |
| **consent_status** | enum | `none` / `market_analysis`（user_submitted 必填） |
| **data_quality** | enum | `verified` / `auto_passed` / `human_reviewed` / `suspect` |
| **soft_requirements** | jsonb | 软性要求数组（experience/education/language 等），每项 `{type, value, evidence_text}`——Match 公式 experience_relevance 的 JD 侧输入（API /api/jd/analyze 的 soft_requirements 即存储于此） |
| parsed_metadata | jsonb | 结构化抽取元信息 |

> 加粗字段为**数据透明性硬约束**（DATA_GOVERNANCE §2），DB 层 NOT NULL + 唯一索引 + CHECK。

### 2.3 company（公司）

| 字段 | 类型 | 说明 |
|---|---|---|
| id / name | PK / text | 海外数据 API 提供标准名 |
| company_type | enum | 大厂/创业/AI 应用公司/金融科技/外企/其他 |
| country | text | 可空 |

### 2.4 skill（技能，共享内核）＆ skill_relation（技能关联）

**skill**：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | |
| **esco_id** | text | ESCO 标准锚点，可空（垂直新技能如 MCP 暂无条目） |
| canonical_name | text(唯一) | 规范名（"LangGraph"） |
| category | enum | Agent Framework / Retrieval / Serving / Engineering / Language / Data / Soft |
| **parent_skill_id** | FK → skill（自引用，可空） | Parent Skill 层级（需求第十七节 Taxonomy 要求；如 "LangGraph → Agent Framework"） |
| **learning_cost** | enum | Low / Mid / High（ROI 公式输入；人工标注，值公开可审计；数值映射见 §4） |
| description / created_at / updated_at | | 词表版本管理 |

**skill_relation**（Related Skill，对称存储双向各一行）—— *为什么需要*：需求第十七节 Taxonomy 要求 + M7 transferable 判定的数据基础（无此表则 transferable 只能靠硬编码）：

| 字段 | 类型 | 说明 |
|---|---|---|
| skill_id / related_skill_id | FK → skill | 联合唯一（含镜像行） |
| relation_type | enum | `related`（同簇近邻）/ `transferable_to`（可迁移，如 Java→Python 工程能力） |
| note | text | 迁移说明（供 UI 展示，如"与 Python 工程能力部分可迁移"） |

### 2.5 skill_alias（别名归一）＆ new_skill_candidate（新词候选）

skill_alias：`skill_id` FK ｜ `alias`(全局唯一) ｜ `language`（zh/en）
new_skill_candidate：`raw_name` ｜ `first_seen_job_id` ｜ `suggested_skill_id`(可空，嵌入排序建议) ｜ `status`(pending/accepted/rejected) —— **为什么需要**：LLM 抽出新词不静默入表也不丢弃，人工周级裁决（DATA_PIPELINE S9）。

### 2.6 job_skill（岗位技能要求）

| 字段 | 类型 | 说明 |
|---|---|---|
| job_id / skill_id | FK | 联合唯一 |
| importance | enum | must_have / nice_to_have |
| intensity | enum | 程度词：精通/熟练/熟悉/了解 → 要求强度 |
| **evidence_text** | text NOT NULL | JD 原文支撑片段（Evidence Layer JD 侧；字符串定位校验） |
| extraction_confidence | numeric | 抽取置信度 |
| extracted_by | enum | llm(model+version) / manual |

### 2.7 candidate ／ candidate_skill ／ candidate_evidence（用户侧）

candidate：本地用户（无账号体系，MVP 冻结）；含 `soft_profile` jsonb——**Match 公式 experience_relevance 的用户侧输入**：`{experience_years, education, languages}`，各字段附 `evidence_text`（来自简历抽取；缺失时置 null，公式按"不可评估"处理，见 §4）。
candidate_skill：`level`(1-5 星) ｜ `confidence`(0-1，证据加权纯函数) ｜ `source_type`(resume_text/manual/github(v2))。
candidate_evidence：`evidence_type`(project_detail 1.0 / project_desc 0.6 / bare_claim 0.3 / manual 1.0) ｜ `evidence_text` ｜ `weight`。
confidence = Σ(weight) 归一化 + 次数衰减——公式纯函数，单测覆盖。

### 2.8 match_result（匹配结果）

| 字段 | 说明 |
|---|---|
| candidate_id / job_id | |
| overall_score | 确定性加权总分 |
| breakdown | jsonb：**coverage / importance_coverage / evidence_quality / experience_relevance 四项**（公式见 §4） |
| strong/weak/missing_skills | jsonb 三组技能 ID |
| explanation | text：LLM 生成解释（只文本，数值由 UI 从 breakdown 渲染） |
| scored_at / **scoring_version** | 评分器版本（semver，与评测结果绑定） |

### 2.9 recommendation（建议）

`candidate_id` ｜ `time_budget_days`(7/14/30) ｜ `priority_items` jsonb（priority/skill_id/demand/gap/cost/potential_gain/rationale）｜ `potential_gain`（**公式计算值** Demand×Gap÷Cost）｜ `project_suggestions`（模板推荐，标注 template 来源）。

### 2.10 market_snapshot（市场统计快照）

| 字段 | 说明 |
|---|---|
| scope | jsonb：**market（china/global，必填）** + 岗位类/城市/时间窗切片 |
| sample_size | **统计必附样本量**（<30 不生成，ADR-008） |
| skill_frequency | jsonb：[{skill_id, frequency, jd_count, evidence_ref}] |
| **source_distribution** | jsonb：tier_a/b/c 及各 source_name 占比 |
| **confidence** | enum：high(N≥200)/medium(50-200)/low(30-50) |
| data_window_start/end、computed_at、method_version | 口径可复现 |

### 2.11 evaluation_sample（评测样本）

`eval_type`(skill_extraction/matching/recommendation/data_quality) ｜ **`input_payload` jsonb（冻结快照副本，非外键引用——Phase 1 落定决策，见 §6）** ｜ `ground_truth` jsonb ｜ annotator/annotated_at ｜ `dataset_version`。

### 2.12 deletion_code（贡献删除凭证）—— *为什么需要：无账号体系下满足用户贡献数据的可删除性（DATA_GOVERNANCE §3）*

`job_id` FK ｜ `code_hash`(唯一) ｜ `created_at`。明文 code 仅贡献成功时一次性展示。

### 2.13 jd_embedding（pgvector 预留表，**不建索引**）—— *为什么需要：Phase 8 RAG 候选场景（ADR-004），表结构预留避免届时迁移*

`job_id` FK ｜ `model` ｜ `dim` ｜ `embedding vector(dim)` ｜ `created_at`。

---

## 3. 关键完整性约束

| 约束 | 实现 |
|---|---|
| JD 去重 | content_hash 唯一索引 |
| 来源透明 | 来源字段 NOT NULL；public_job_page → source_url 必填；user_submitted → consent_status 必填（CHECK） |
| 市场分离 | market NOT NULL + 统计 SQL 强制 group by market（无"全市场混合"统计路径） |
| 统计守门 | 应用层：snapshot 生成前校验 sample_size ≥30 |
| 证据完整 | job_skill.evidence_text NOT NULL；candidate_skill 至少一条 evidence |
| 只统计可信数据 | 统计查询 WHERE status='active' **AND (source_type != 'user_submitted' OR consent_status='market_analysis')**（未授权贡献数据永不进入统计——B1 修复，2026-08-31 评审） |
| 共享内核一致性 | skill_alias.alias 全局唯一；评测集与词表版本一致性由 CI 保证 |

---

## 4. Match Score 公式与数值映射（Phase 1 冻结设计，权重为 configurable heuristic，Phase 7 E2 校准）

### 4.1 公式

```
required_weight(s)  = 3 (must_have) / 1 (nice_to_have)
conf_factor(s)     = 0.5 + 0.5 × confidence(s)          # 证据充分的技能贡献更高
coverage           = Σ ach_w / Σ req_w
                     ach_w = required_weight × conf_factor（满足时）
importance_coverage = Σ must_have 满足权重 / Σ must_have 总权重
evidence_quality   = mean(confidence of matched skills)
experience_relevance = 软性要求（年限/学历/语言）匹配率

Overall = 100 × (0.45×coverage + 0.25×importance_coverage
           + 0.20×evidence_quality + 0.10×experience_relevance)
```

**权重依据**：技能覆盖是招聘筛选主体（最大）；must_have 一票否决文化（次之）；证据置信度是本项目差异化（第三）；经验相关性数据最弱、仅作参考（最小）。全部标记 **configurable heuristic**，E2 标注集验证后修订并升 scoring_version。

### 4.2 枚举→数值映射表（公式代入专用，展示层仍用枚举）

| 枚举 | 数值 | 用途 |
|---|---|---|
| 程度词（job_skill.intensity → required_level） | 精通=5 ｜ 熟练=4 ｜ 熟悉=3 ｜ 了解=2 ｜ nice_to_have 封顶 2 | Gap 计算（M7） |
| 学习成本（skill.learning_cost → cost_value） | Low=1 ｜ Mid=2 ｜ High=3 | ROI 公式除数 |
| candidate_skill.level | 1-5 星 = 1-5 | Gap 计算（actual_level） |

### 4.3 除零与空值守卫（冻结：中性值 0.5 策略）

| 分母为 0 / 不可评估的场景 | 规则 |
|---|---|
| JD 无任何技能抽取结果（Σreq_w=0） | coverage=0，match_result 标记 `invalid: no_skills`，UI 明示"该 JD 无法评分" |
| JD 无 must_have（importance 分母=0） | importance_coverage = 0.5（中性） |
| 无匹配技能（evidence_quality 无样本） | evidence_quality = 0.5（中性） |
| soft_profile 缺失 / 软性要求全部不可评估 | experience_relevance = 0.5（中性） |

### 4.4 Gap 与 transferable 判定（M7 冻结）

```
required_level(s) = intensity 映射值（§4.2，nice_to_have 封顶 2）
actual_level(s)  = candidate_skill.level
gap(s)           = clamp(required_level − actual_level, ≥ 0)

transferable 判定（确定性规则，Phase 6 实现）：
  缺口技能 s 为 genuine gap   ⇔ 用户对 s、s 的 parent、s 的 skill_relation(relation_type=transferable_to)
                                 目标技能均无证据（confidence < 0.5 或无记录）
  缺口技能 s 为 transferable  ⇔ 存在 transferable_to 关联技能 t 且用户 t 有证据（confidence ≥ 0.5）
```

**注意**：confidence 影响 match 分数与 strong/weak 判定（conf_factor），**不直接进 gap**（gap 是星级差）；二者分离是 F6/F7 口径统一的依据（2026-08-31 评审 H1 修复）。

---

## 5. 词表 v1

### 5.1 job_category 枚举（源自 MARKET_RESEARCH §5.1 岗位名收敛）

`ai_application_dev`（AI 应用开发，最常见）｜`agent_dev`（Agent 开发）｜`llm_fullstack`（AI 全栈）｜`mcp_dev`（MCP/Skill 开发）｜`ai_platform`（AI 平台/工程化）｜`python_ai_dev`｜`dify_dev`｜`other`。海外源（Adzuna category）经映射表归一到本枚举，映射关系随词表版本管理。

### 5.2 技能词表 v1（源自 MARKET_RESEARCH §2.2/§2.3，25-30 个垂直技能 + ESCO 锚点）

Python、Java、LLM 应用开发、LangChain、LangGraph、AutoGen、CrewAI、RAG、Prompt Engineering、MCP、Dify、FastAPI、Docker、Kubernetes、PostgreSQL、MySQL、Redis、pgvector、Milvus、Chroma、Qdrant、Neo4j、SFT/LoRA、vLLM、Evaluation（LLM 评测）、多模态、Function Calling、ReAct、上下文管理、AI Coding。
每个技能含 category / learning_cost / alias（中英）——**词表每个技能的频率声明必须由自建数据集验证，不允许凭印象写进产品**（MARKET_RESEARCH §2.3 纪律）。

---

## 6. Phase 0 遗留决策落定（原 §5）

| 遗留决策 | Phase 1 落定 |
|---|---|
| job_category 枚举词表 | §5.1 收敛为 8 类 + 海外源映射表 |
| pgvector 表结构 | §2.13 预留表（不建索引，ADR-004） |
| 评分器 versioning | scoring_version 语义化版本，评测结果绑定版本三元组（prompt, model, dataset）+ scoring_version |
| 评测集引用方式 | **冻结快照副本**（input_payload 存入 evaluation_sample，非外键）——理由：评测复现性优先于存储成本；业务数据可删除而评测不失效 |

---

## 7. Demo Dataset 规格

| 项 | 规格 |
|---|---|
| 规模 | 中国市场 200-300 条中文 JD（MVP.md §3）＋ Global 市场首批 Adzuna 拉取（按免费额度） |
| 切片 | AI 应用开发为主，覆盖 §5.1 全部岗位类别；北上深杭为主 + 2-3 个高增长城市 |
| 来源构成 | 公开页面合规摘录（记 source_url）+ 用户手动录入 |
| 格式 | CSV/JSON（列 = job 表字段 + 建议标注技能清单） |
| 导入 | import 命令：校验 → 去重 → 入库 → 导入报告（新增/重复/失败） |
| 验收 | 导入后频率统计与抽样人工核对一致；来源字段 100% 完整；中国市场与全球市场零混淆 |
