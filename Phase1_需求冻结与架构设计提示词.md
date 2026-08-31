# SkillGap Agent —— Phase 1：需求冻结 + 产品架构 + 数据架构设计提示词

> 原始文件为 Word 文档（上传时扩展名为 .md），此处保存提取后的完整正文作为需求原始记录。
> 提取时间：2026-08-31 ｜ 文档中 "JobLens" 为项目暂定名，正式名 SkillGap Agent（Phase 0 决议）

Phase 0 已经完成。

你现在需要基于 Phase 0 的研究结果，进入 Phase 1：需求冻结、产品设计、系统架构和数据架构设计。

本阶段禁止编写业务代码。

最终目标不是设计一个"技术栈很复杂"的项目，而是把 Phase 0 的市场研究真正转化为一个：

«有真实用户问题、有真实数据来源、有明确技术难点、有可验证 Evaluation、有工程化价值的 AI 应用。»

---

## 一、最高优先级原则

1. 不要为了技术而技术

不要因为：
- Agent 很热门
- RAG 很热门
- LangGraph 很热门
- Redis 很热门
- Docker 很热门
- pgvector 很热门

就强行加入。

每一个技术必须回答：
«为什么这个业务问题需要它？»

如果普通 Python / SQL / FastAPI 就能解决：
优先使用简单方案。

---

## 二、不要重新做 Phase 0

Phase 0 已经完成：
- 市场研究
- 竞品研究
- GitHub 开源项目研究
- 岗位需求分析

现在必须读取并利用 Phase 0 的结果。

重点读取：
MARKET_RESEARCH.md
COMPETITOR_ANALYSIS.md
OPEN_SOURCE_RESEARCH.md

以及 Phase 0 产生的其他研究文件。

不要无意义重复调研。

如果发现 Phase 0 的结论与最初 JobLens 设想冲突：
«以 Phase 0 的研究结论为准。»

允许：
- 修改功能
- 删除功能
- 重构产品方向
- 调整技术路线

甚至可以在发现明显更好的方向时推翻原方案。

---

## 三、最重要的数据源原则

项目明确禁止爬虫

这是硬约束。

禁止开发任何针对招聘平台的爬虫。

尤其禁止：
- BOSS 直聘爬虫
- 牛客爬虫
- 拉勾爬虫
- 智联招聘爬虫
- 猎聘爬虫
- 绕过登录限制
- 绕过验证码
- 绕过反爬
- 模拟用户行为批量采集
- 未经许可抓取受限制的数据

不要因为"需要真实国内岗位数据"就破坏这个原则。

---

## 四、国内岗位数据怎么解决

必须把数据架构设计成：

```
JobLens Data Sources
│
┌─────────────────┼─────────────────┐
│                 │                 │
↓                 ↓                 ↓
Public APIs      Public Job Pages    User Submitted
│                 │                 │
海外公开岗位       公司招聘官网       用户主动粘贴 JD
公开 Job API      学校/机构招聘页     CSV / JSON
│                 │                 │
└─────────────────┼─────────────────┘
↓
Data Ingestion Layer
↓
Normalization
↓
Deduplication
↓
PII Redaction
↓
Quality Validation
↓
Job Dataset
```

核心思想

我们不需要：
«"获取 BOSS 的全部数据。"»

而是：
«获得足够真实、可追溯、合法来源的中国就业市场 JD。»

---

## 五、用户贡献 JD

这是 JobLens 的重要产品机制。

用户在 BOSS / 牛客 / 其他招聘软件看到岗位后，可以：

```
复制 JD
↓
粘贴到 JobLens
↓
分析 JD
↓
得到 Skill Analysis
↓
用户可选择：
"匿名贡献到市场数据集"
```

如果用户同意：

```
User Submitted JD
↓
PII Detection
↓
PII Redaction
↓
Content Hash
↓
Deduplication
↓
Skill Extraction
↓
Quality Validation
↓
Market Dataset
```

必须明确：
«用户主动提交数据和平台自动抓取数据是完全不同的。»

---

## 六、用户贡献数据的隐私设计

必须考虑：
- 手机号
- 邮箱
- 联系人姓名
- 微信号
- QQ
- 公司内部敏感信息
- 个人身份信息

在进入市场统计数据集之前：
«尽可能进行 PII Detection + Redaction。»

例如：
```
138xxxxxxxx
↓
[PHONE_REDACTED]

xxx@qq.com
↓
[EMAIL_REDACTED]
```

但不要声称：
«"100% 可以自动删除所有个人隐私。"»

必须保留人工/规则校验的可能性。

---

## 七、数据来源必须透明

每条 Job 数据必须记录来源。

建议：
source_type
source_name
source_url
collected_at
submitted_at
content_hash
license_or_usage_note
consent_status
data_quality

例如：
source_type = public_api
source_name = Adzuna

或者：
source_type = user_submitted
source_name = community
consent_status = market_analysis

如果来源是公司招聘官网：
source_type = public_job_page
source_name = company_career_page
source_url = ...

---

## 八、数据源分级

设计一个 Data Source Trust Model。

例如：
Tier A
公开 API
公司官方招聘页面
公开机构招聘页面

Tier B
用户主动提交 JD

Tier C
其他经过许可的数据源

具体分级根据 Phase 0 和实际情况调整。

不要把：
«"用户提交的 1 条 JD"»
和：
«"公开 API 的大量结构化数据"»
混在一起不加区分。

---

## 九、市场数据必须展示样本量

系统绝对不能告诉用户：
«"中国 AI 岗位中 Python 占 82%。"»
如果实际上只有 30 条样本。

必须显示：

```
Skill:
Python

Frequency:
24 / 30
80%

Sample Size:
30

Data Sources:
Public API
User Submitted

Confidence:
Low
```

如果样本量不足：
«明确告诉用户当前样本不足。»

禁止：
- 编造统计数据
- LLM 猜市场趋势
- 用少量样本代表整个中国市场
- 把国外市场数据直接当成中国市场

---

## 十、海外公开岗位

海外公开岗位可以作为：
«第一阶段稳定、可自动化的数据来源。»

研究可用的：
- Public Job APIs
- 公开招聘数据
- 公司 Career Pages
- 公开就业数据

例如可以研究：
«Adzuna API»

但必须检查：
- API 使用限制
- 数据许可
- 商业使用限制
- Attribution 要求
- Rate Limit

不能默认任何 API 都可以无限制使用。

---

## 十一、国内市场与海外市场必须区分

数据库中必须能够区分：
country
region
market
language
source_type

例如：
China
United States
United Kingdom

最终市场分析必须支持：
China Market
Global Market

不能把两个市场的数据混成一个统计结果。

---

## 十二、建立 Market Snapshot

设计：
MarketSnapshot

用于保存某一时间窗口的市场统计。

例如：
```
Market:
China

Period:
2026-08-01 ~ 2026-08-31

Sample Size:
1240

Top Skills:
Python
RAG
Agent
FastAPI
Docker
```

以后才能支持：
«7 天 / 30 天 / 90 天趋势。»

但只有在样本量足够时才允许计算趋势。

---

## 十三、数据 Pipeline

设计：

```
Source
↓
Ingestion
↓
Raw Data
↓
Normalization
↓
PII Detection
↓
Redaction
↓
Deduplication
↓
Validation
↓
Skill Extraction
↓
Skill Normalization
↓
Job Dataset
↓
Market Analytics
```

明确：
«哪一步由代码完成？»
«哪一步由 LLM 完成？»
«哪一步需要人工校验？»

---

## 十四、Deterministic Layer / LLM Layer / Evidence Layer

系统必须尽量形成：

```
Deterministic Layer
+
LLM Layer
+
Evidence Layer
```

Deterministic Layer
优先由代码完成：
- 数据清洗
- PII 正则检测
- Hash
- 去重
- 统计
- 排序
- Match Score
- 数据校验
- 状态管理

LLM Layer
用于：
- JD 理解
- Skill Extraction
- Skill Normalization
- 语义分类
- 自然语言解释
- Recommendation Explanation

Evidence Layer
保存：
- JD 原文
- Skill 来源
- 用户项目证据
- Match 原因
- Recommendation 原因
- Source

---

## 十五、MVP

输出：
docs/MVP.md

重新定义最终 MVP。

必须包含：

Must Have
第一版必须实现。

Should Have
重要但可以后置。

Could Have
未来增强。

Won't Have
明确不做。

特别注意：
«禁止把"自动爬 BOSS"放进任何版本。»

---

## 十六、核心 MVP 闭环

最终 MVP 至少需要形成：

```
User
↓
Paste Resume / JD
↓
JD Analysis
↓
Skill Extraction
↓
Skill Normalization
↓
Candidate Profile
↓
Job Matching
↓
Skill Gap
↓
Recommendation
↓
Evidence
```

如果市场数据已经达到足够规模，再增加：
Market Intelligence

---

## 十七、Skill Taxonomy

根据 Phase 0 的真实岗位数据建立 Skill Taxonomy。

需要支持：

```
Skill
├── Category
├── Alias
├── Synonym
├── Parent Skill
└── Related Skill
```

例如：
```
Postgres
PostgreSQL
PG
统一：
PostgreSQL
```

但不能只靠字符串匹配。

需要设计：
«LLM + Rule + Validation»

---

## 十八、Candidate Evidence

用户说：
«"我会 RAG。"»

系统不能直接认为：
«Skill = RAG，Confidence = 100%。»

应该尽可能寻找证据：
Resume
Project
README
Code
Dependency

例如：
```
Skill:
RAG

Evidence:
Project A
- Hybrid Search
- RRF
- Rerank

Confidence:
0.91
```

具体评分方式需要设计和验证。

---

## 十九、Job Matching

输入：
Candidate
+
Job

输出：
Match Score
Strong Skills
Weak Skills
Missing Skills
Evidence

必须回答：
«为什么匹配？»

而不是只输出：
«78%。»

---

## 二十、Match Score

禁止：
LLM → "你匹配度 78%"
直接作为最终结果。

优先设计：

```
Match Score =
Skill Coverage
+
Skill Importance
+
Evidence Confidence
+
Experience Relevance
```

具体公式必须由你根据 Phase 0 研究设计。

权重必须有依据。

如果无法证明：
标记：
configurable heuristic

然后交给 Evaluation 验证。

---

## 二十一、Recommendation

最终系统需要回答：
«"我现在最应该补什么？"»

例如：

```
Skill Gap
↓
Market Demand
↓
Learning Cost
↓
Potential Benefit
↓
Priority
```

输出：
```
Priority 1
FastAPI

原因：
目标岗位需求较高
当前证据不足
学习成本相对低
补齐后可覆盖更多岗位
```

注意：
«不允许让 LLM 随便编一个 ROI 数字。»
必须设计计算逻辑。

---

## 二十二、项目推荐

如果用户缺少某个技能：
不要只说：
«"去学习 MCP。"»

可以推荐：

```
Skill Gap
↓
Project Template
↓
Expected Skills
↓
Estimated Effort
```

例如：
```
MCP + RAG Agent
2~3 days

Skills:
MCP
RAG
Tool Calling
Agent
```

但这个项目推荐功能是否属于 MVP：
«根据 Phase 0 研究决定。»

---

## 二十三、Agent

不要为了简历强行 Multi-Agent。

只有在任务确实需要：
- 多步骤决策
- 状态管理
- 工具调用
- 循环
- 动态路径

时才使用 Agent / LangGraph。

如果普通 Workflow 更合理：
«使用 Workflow。»

必须记录架构取舍。

---

## 二十四、RAG

如果需要 RAG：
RAG 必须解决实际问题。

例如：
«用户问"为什么推荐我学习 MCP？"»
系统可以检索：
- 岗位数据
- Skill 数据
- 用户证据
然后生成：
«有依据的解释。»

不要为了展示 RAG 而做一个：
«"上传 PDF → 聊天"»
的普通 Demo。

---

## 二十五、Evaluation

现在就设计。
不要等项目完成之后再补。

输出：
docs/EVALUATION_PLAN.md

至少包含：

Skill Extraction
- Precision
- Recall
- F1

Matching
- Precision
- Recall
- F1
- Correlation（如果合理）

Recommendation
定义可验证指标。

整体结构：
```
Dataset
↓
Ground Truth
↓
System
↓
Prediction
↓
Metrics
↓
Report
```

---

## 二十六、数据质量 Evaluation

增加：
Data Quality Evaluation

至少考虑：
- Duplicate Rate
- Missing Field Rate
- PII Detection
- Invalid JD Rate
- Skill Extraction Error Rate

这样项目不只是：
«AI 应用»
还有：
«数据工程能力。»

---

## 二十七、数据模型

输出：
docs/DATA_MODEL.md

考虑：
```
Job
Company
Skill
SkillAlias
JobSkill
Candidate
CandidateSkill
CandidateEvidence
MatchResult
Recommendation
MarketSnapshot
EvaluationSample
DataSource
```

不要为了显得复杂而全部建立。

每张表必须说明：
«为什么需要？»

---

## 二十八、API

输出：
docs/API.md

根据最终 MVP 设计。

可能包括：
```
POST /api/jobs/analyze
POST /api/resumes/analyze
POST /api/match
GET /api/market/skills
GET /api/candidates/{id}/gaps
POST /api/recommendations
POST /api/jobs/import
```

但不要机械照抄。

每个 API 说明：
- Method
- Path
- Request
- Response
- Error
- 是否同步
- 是否需要 LLM
- 数据来源

---

## 二十九、LLM Provider

设计：

```
LLMProvider
├── generate()
├── generate_structured()
└── embed()
```

业务层不要直接依赖某个厂商 SDK。

第一版只需要一个实际 Provider。

---

## 三十、错误处理

设计：
```
Validation Error
LLM Error
Timeout
Rate Limit
Database Error
External API Error
Invalid Data
```

确定：
- Timeout
- Retry
- Fallback
- Logging
- Error Response

不要过度设计。

---

## 三十一、可观测性

根据实际复杂度决定是否需要：
- Request ID
- Structured Logging
- LLM latency
- Token usage
- Error rate
- Trace

如果 Agent 使用 LangGraph：
再考虑：
- Node execution
- Tool execution
- State transition

---

## 三十二、前端

输出：
docs/UI_SPEC.md

不要先做花哨 UI。

MVP 页面优先：

Dashboard
展示：
- 用户技能
- 市场技能
- Skill Gap
- Match Score
- Recommendation

JD Analysis
Resume Analysis
Job Matching
Recommendation

重点：
«展示数据、证据和决策。»

不要做成一个只有聊天框的 AI 产品。

---

## 三十三、系统架构

输出：
docs/ARCHITECTURE.md

至少设计：

```
Frontend
↓
FastAPI
↓
Application Layer
↓
Domain / Decision Layer
↓
AI / Data Layer
↓
PostgreSQL
```

根据实际需求决定是否增加：
pgvector
Redis
Task Queue
LangGraph
Reranker

每一个都必须说明：
«为什么需要。»

---

## 三十四、数据架构

必须单独设计：
docs/DATA_PIPELINE.md

描述：

```
Public API
│
Public Job Pages
│
User Submitted JD
│
CSV / JSON
↓
Ingestion
↓
Normalization
↓
PII Redaction
↓
Deduplication
↓
Validation
↓
Skill Extraction
↓
Skill Normalization
↓
PostgreSQL
↓
Market Analytics
```

必须明确每一步：
- 输入
- 输出
- 失败处理
- 是否使用 LLM
- 是否需要人工审核

---

## 三十五、数据合规原则

建立：
docs/DATA_GOVERNANCE.md

至少说明：
- 数据来源
- 用户主动提交机制
- PII 处理
- 数据保留策略
- 删除机制
- Source Attribution
- API Terms
- 禁止爬虫
- 禁止绕过平台限制

尤其明确：
«JobLens 不通过爬虫获取 BOSS、牛客等招聘平台数据。»

---

## 三十六、Architecture Decision Record

创建：
docs/adr/

至少记录：

ADR-001
为什么不爬招聘平台？

ADR-002
为什么采用 Public API + Public Job Pages + User Submitted JD？

ADR-003
为什么 PostgreSQL？

ADR-004
为什么/为什么不使用 pgvector？

ADR-005
为什么 LLM 不负责最终 Match Score？

ADR-006
为什么/为什么不使用 LangGraph？

ADR-007
为什么需要 Evidence？

ADR-008
为什么市场统计必须显示 Sample Size？

每个 ADR：
```
Context
Options
Pros
Cons
Decision
```

---

## 三十七、最终文档

Phase 1 完成后至少应该存在：

```
docs/
├── MVP.md
├── PRODUCT_SPEC.md
├── ARCHITECTURE.md
├── DATA_MODEL.md
├── DATA_PIPELINE.md
├── DATA_GOVERNANCE.md
├── API.md
├── UI_SPEC.md
├── EVALUATION_PLAN.md
├── DECISION_LOG.md
└── adr/
```

---

## 三十八、Phase 1 Review

最后创建：
PHASE_1_REVIEW.md

回答：
1. 最终产品是什么？
2. 解决什么真实问题？
3. 为什么这个问题值得解决？
4. MVP 是什么？
5. 删除了哪些原始功能？
6. 为什么删除？
7. 数据从哪里来？
8. 中国岗位数据怎么获得？
9. 为什么不爬 BOSS？
10. 用户贡献数据怎么工作？
11. 如何保护用户隐私？
12. 当前系统架构是什么？
13. 为什么这样设计？
14. 最大技术风险是什么？
15. 最大数据风险是什么？
16. 最大产品风险是什么？
17. 最难实现的部分是什么？
18. 哪些地方最值得写进简历？
19. 哪些功能虽然听起来高级但应该暂时不做？
20. Phase 2 应该先做什么？

---

## 三十九、Phase 1 完成后停止

非常重要：

Phase 1 完成后不要自动进入 Phase 2。

不要：
- 写业务代码
- 创建数据库
- 创建前端
- 自动安装大量依赖
- 自动生成 Docker
- 自动开始开发

先完成全部设计文档。

然后：
«停止并等待我的确认。»

---

## 最终原则

这个项目不是为了：
«"堆一堆 AI 技术然后写进简历。"»

而是为了：
«用真实就业市场数据解决求职者"市场需要什么、我缺什么、我下一步该做什么"的问题。»

因此：
```
数据真实性 > 技术炫技
可验证性 > LLM 说得漂亮
简单可靠 > 过度工程化
真实需求 > 简历关键词
Evidence > 空口结论
Evaluation > 主观感觉
```

特别注意：
«禁止爬虫是项目的硬约束，不是一个需要绕过的问题。»

中国岗位数据采用：
«用户主动提交 JD + 公开招聘页面 + 合法公开 API / 数据源»

海外岗位采用：
«合法公开 API / 公开招聘页面»

所有数据必须记录来源、时间和质量信息。

现在开始 Phase 1。

不要写代码。
