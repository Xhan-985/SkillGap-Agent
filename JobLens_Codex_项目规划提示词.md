# JobLens：AI 就业市场智能分析与技能决策 Agent

## 项目定位

我要开发一个真正可以放进求职简历、能够体现 **LLM / RAG / Agent / 数据工程 / 推荐决策 / Evaluation / 工程化** 能力的项目。

项目暂定名称：

> **JobLens —— AI 就业市场智能分析与技能决策 Agent**

我目前已经有两个 AI 应用项目：

1. 一个偏 **RAG / Hybrid Search / RRF / Rerank / LLM Evaluation**
2. 一个偏 **Agent / LangGraph / Trace / Replay / Observability**

第三个项目不要重复前两个项目。

我要通过第三个项目补充：

- 真实数据处理
- 就业市场分析
- Skill Extraction
- Skill Graph / Skill Taxonomy
- Job Matching
- Skill Gap Analysis
- Recommendation
- Agent 决策
- 数据驱动的产品设计
- Evaluation
- AI 应用工程化

最终形成：

> **RAG + Agent + Evaluation + Data + Recommendation + Real-world Product**

而不是再做一个普通聊天机器人。

---

# 一、核心问题

现在很多年轻人找 AI / 软件开发工作时面临一个问题：

他们知道：

> Python、Java、RAG、Agent、MCP、LangGraph、Docker……

但不知道：

> **市场现在到底需要什么？**

也不知道：

> **我现在的能力距离目标岗位到底差多少？**

更不知道：

> **如果我只有 7 天 / 14 天 / 30 天，我应该优先补什么？**

所以 JobLens 要解决：

> **市场需要什么 → 用户有什么 → 用户缺什么 → 哪些岗位值得投 → 接下来做什么最有价值**

---

# 二、核心产品闭环

```text
真实招聘数据
      ↓
JD 清洗
      ↓
技能/要求抽取
      ↓
岗位技能结构化
      ↓
市场需求分析
      ↓
用户简历 / 项目分析
      ↓
用户技能画像
      ↓
Skill Gap Analysis
      ↓
岗位匹配
      ↓
优先级决策
      ↓
学习 / 项目 / 求职建议
      ↓
用户反馈
      ↓
Evaluation
      ↓
持续优化
```

---

# 三、第一原则：不要先写代码

第一阶段禁止直接开始开发。

先完成：

## Phase 0 —— 市场与竞品研究

你需要研究：

### 1. 当前真实 AI 应用开发岗位

重点观察：

- Python
- Java
- RAG
- Agent
- LangGraph
- LangChain
- MCP
- FastAPI
- Docker
- PostgreSQL
- Redis
- Evaluation
- Observability
- AI Coding
- LLM
- Prompt
- 向量数据库

但不要默认这些都是重要的。

必须通过真实岗位数据验证：

> **哪些技能真的高频？**

---

# 四、招聘数据来源

研究并评估：

- BOSS 直聘
- 牛客
- 拉勾
- 智联招聘
- 猎聘
- 公司官方招聘网站
- 公开招聘页面

重点考虑：

> **合法、稳定、可持续的数据来源。**

不要把整个项目建立在脆弱的反爬虫方案上。

禁止：

- 破解验证码
- 绕过登录限制
- 绕过反爬机制
- 非法获取用户隐私数据

第一版必须支持：

> **用户手动粘贴 JD**

所以即使实时数据源全部失效，系统仍然能够运行。

---

# 五、GitHub 开源项目研究

研究 GitHub 上与以下方向相关的开源项目：

### Job / Career

- job matching
- career advisor
- resume matching
- skill extraction
- job recommendation

### AI

- RAG
- Agent
- LangGraph
- recommendation
- evaluation

### Data

- job market analytics
- NLP skill extraction
- taxonomy

重点不是复制项目。

我要你分析：

> 它们解决了什么问题？

> 使用了什么架构？

> 哪些设计值得借鉴？

> 哪些设计明显不足？

> 我们能不能做得更好？

如果 GitHub 项目已经解决了类似问题：

**不要假装我们是第一个。**

我们的差异化必须来自：

> **市场数据 → 技能需求 → 用户能力 → Skill Gap → 决策建议 → Evaluation**

---

# 六、竞品研究

研究：

- AI 简历优化器
- AI Job Matcher
- Career Advisor
- AI Interview Coach
- Job Recommendation

最终输出：

`COMPETITOR_ANALYSIS.md`

必须包含：

| 产品 | 解决的问题 | 核心功能 | 技术特点 | 优点 | 缺点 | 我们是否需要 |
|---|---|---|---|---|---|---|

最后明确：

> **JobLens 不应该做什么。**

---

# 七、确定 MVP

研究完成后，不要无限加功能。

必须严格控制 MVP。

我初步建议 MVP 包含：

## 1. JD Analyzer

用户：

> 粘贴一个招聘 JD

系统输出：

```text
岗位：
AI 应用开发实习生

核心技能：
Python
RAG
Agent
FastAPI

次要技能：
Docker
Redis
PostgreSQL

软性要求：
...
```

---

# 八、Skill Extraction

不能只做字符串关键词匹配。

建立：

```text
Skill
 ├── Category
 ├── Alias
 ├── Related Skill
 ├── Importance
 └── Evidence
```

例如：

```text
LangGraph
↓
Agent Framework
↓
Agent Development
```

---

# 九、Job Market Intelligence

当系统积累一定数量的 JD 后：

分析技能出现频率。

例如：

```text
Python       82%
RAG          71%
Agent        68%
Docker       44%
FastAPI      41%
MCP          32%
```

但必须注意：

> 这些数字必须来自真实数据。

不能让 LLM 编造。

---

# 十、技能趋势

如果数据量允许：

分析：

> 最近 7 / 30 / 90 天技能变化。

例如：

```text
MCP       ↑
Agent     ↑
RAG       →
LoRA      →
```

如果数据不足：

明确告诉用户：

> 当前样本量不足以判断趋势。

不要伪造趋势。

---

# 十一、用户能力画像

用户可以：

### 方式 A

上传 PDF 简历。

### 方式 B

粘贴简历文本。

### 方式 C

填写技能。

### 方式 D

输入 GitHub Repository。

如果用户输入 GitHub：

分析公开仓库中的：

- README
- languages
- repository structure
- commit activity
- dependency
- tests
- CI
- documentation

但必须区分：

> **“项目声明使用了什么”**

和：

> **“代码实际证明使用了什么”。**

不要因为 README 写了某技术就默认用户掌握。

---

# 十二、Skill Gap Analysis

这是整个项目的核心。

例如：

```text
目标岗位：
AI Application Developer

岗位要求：
Python       ★★★★★
RAG          ★★★★★
Agent        ★★★★
FastAPI      ★★★★
Docker       ★★★
MCP          ★★★

用户：
Python       ★★★★
RAG          ★★★★★
Agent        ★★★★
FastAPI      ★★
Docker       ★★★
MCP          ★
```

然后输出：

> **最大技能缺口：FastAPI、MCP**

---

# 十三、不要简单做“关键词匹配”

设计：

## Evidence-based Skill Matching

每个技能必须有证据。

例如：

```text
Skill:
RAG

Evidence:
Project A
├── pgvector
├── Hybrid Search
├── RRF
└── Rerank

Confidence:
0.91
```

如果简历只写：

> 熟悉 RAG

则：

```text
Confidence:
0.45
```

这样系统才真正有意义。

---

# 十四、岗位匹配

输入：

> 用户能力画像 + JD

输出：

```text
Overall Match:
78%

Strong:
RAG
Agent
PostgreSQL

Weak:
FastAPI

Missing:
MCP
```

同时解释：

> 为什么是 78%。

不要出现：

> “AI 判断你匹配度为 78%。”

必须给出可解释依据。

---

# 十五、建立“技能投资回报率”

这是核心创新点之一。

用户输入：

> 我只有 7 天。

系统计算：

```text
Skill       Demand    Gap    Cost    Potential Gain

FastAPI     41%       High   Low     +22%
MCP         32%       High   Low     +18%
vLLM        18%       High   Mid     +8%
LoRA        15%       High   High    +4%
```

最终：

> 推荐优先学习 FastAPI + MCP。

这里的“Potential Gain”必须基于明确计算逻辑。

不要让 LLM 随便拍一个数字。

---

# 十六、推荐系统

最终 Agent 应该能够回答：

> “我下一步应该做什么？”

例如：

### Priority 1

补 FastAPI。

原因：

> 目标岗位 41% 出现  
> 当前能力证据不足  
> 学习成本低  
> 对岗位覆盖影响大

### Priority 2

做一个 MCP Tool 项目。

### Priority 3

学习 vLLM。

---

# 十七、项目推荐

如果系统发现：

> 用户缺 MCP

不要只告诉：

> 学 MCP。

而是：

> **给用户推荐一个能够证明 MCP 能力的小项目。**

例如：

```text
项目：
MCP + RAG Knowledge Agent

预计时间：
2~3 天

证明技能：
MCP
RAG
Tool Calling
Agent

目标：
让用户通过这个项目补齐 JD 中的技能缺口。
```

这就形成：

> **就业市场 → 技能缺口 → 项目推荐**

---

# 十八、Agent 不是为了“有 Agent 而 Agent”

Agent 只能用于真正需要推理和决策的地方。

建议：

```text
Market Analyst Agent
        ↓
Skill Analyst Agent
        ↓
Candidate Analyst Agent
        ↓
Gap Analyst Agent
        ↓
Career Planner Agent
```

但不要为了展示 Multi-Agent 就强行拆成 5 个 Agent。

如果单 Agent + Workflow 更合理：

**使用单 Agent。**

必须解释架构取舍。

---

# 十九、RAG

RAG 可以使用在：

> JD / Skill / Career Knowledge

例如用户问：

> “为什么推荐我学习 MCP？”

系统需要能够引用：

> 哪些岗位要求 MCP。

也就是说：

**建议必须能够追溯到真实数据。**

---

# 二十、Evaluation

这是必须有的。

至少建立：

## JD Skill Extraction Evaluation

人工标注一批 JD：

```text
JD
↓
Ground Truth Skills
↓
Model Extraction
↓
Precision / Recall / F1
```

---

## Job Matching Evaluation

建立人工标注：

```text
JD + Candidate
↓
Human Match Score
↓
System Match Score
```

计算：

- Accuracy
- Precision
- Recall
- F1
- Correlation

---

## Recommendation Evaluation

测试：

> 系统推荐的技能是否真的与岗位需求相关？

---

# 二十一、不要让 LLM 成为“万能黑盒”

这是项目的重要设计原则。

例如：

### 频率统计

必须：

> SQL / Python 统计

不能：

> LLM 判断。

### 匹配分数

尽量：

> Deterministic scoring

LLM 负责：

> 解释。

### Skill Extraction

可以：

> LLM + Schema

然后：

> Validation + Normalization

### Recommendation

可以：

> Rule + Ranking + LLM Explanation

最终形成：

```text
Deterministic Layer
        +
LLM Layer
        +
Evidence Layer
```

---

# 二十二、数据模型

你需要设计至少：

```text
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
```

但不要为了显得复杂而设计无意义表。

先给出 ER 图。

---

# 二十三、技术栈

默认优先：

### Backend

Python

FastAPI

### Database

PostgreSQL

pgvector

### AI

当前主流 LLM API

Structured Output

Embedding

### Agent

LangGraph

### Cache

Redis

### Data

Pandas

### Deployment

Docker Compose

### Testing

pytest

### CI

GitHub Actions

但：

> **不要为了覆盖技术栈而使用技术。**

每一个技术都必须回答：

> 为什么需要？

---

# 二十四、必须支持 Provider Abstraction

LLM 不要硬编码。

设计：

```text
LLMProvider
├── OpenAI-compatible
├── Local Model
└── Other Provider
```

未来可以接：

> DeepSeek / Qwen / GLM / OpenAI-compatible API

但第一版不要同时实现所有 Provider。

---

# 二十五、前端

不要做一个花里胡哨的 AI Chat 页面。

核心 Dashboard：

```text
我的就业画像

      Match Score

技能雷达

市场热门技能

我的技能缺口

推荐学习

推荐项目

目标岗位
```

重点展示：

> **数据和决策**

而不是：

> 一个聊天框。

---

# 二十六、用户核心流程

最终必须可以完整走通：

```text
注册 / 本地用户
      ↓
上传简历
      ↓
分析能力
      ↓
选择目标岗位
      ↓
JobLens 分析市场
      ↓
Skill Gap
      ↓
岗位匹配
      ↓
技能投资回报
      ↓
学习计划
      ↓
项目推荐
```

---

# 二十七、必须有 Demo Dataset

不要要求我先去爬 10 万条数据。

项目第一版必须内置：

> 经过清洗的 Demo JD Dataset

例如：

> 100~500 条

具体数量根据研究决定。

同时支持：

> CSV / JSON 导入。

这样整个项目能够：

> clone → docker compose → import dataset → run

---

# 二十八、数据来源必须透明

数据库中的每个 JD：

```text
source
source_url
collected_at
content_hash
```

如果数据来自人工录入：

明确：

> manual_import

如果来自公开网页：

记录：

> source_url

---

# 二十九、前卫功能候选

研究后，如果 MVP 稳定，可以考虑：

### 1. Job Market Radar

实时市场技能变化。

### 2. Career What-if

例如：

> 如果我花 14 天学习 MCP，会增加哪些岗位匹配？

### 3. Project ROI

> 做哪个项目最能弥补技能缺口？

### 4. Skill Graph

```text
RAG
├── Embedding
├── Retrieval
├── Rerank
└── Evaluation
```

### 5. Resume Evidence Graph

简历上的一句话：

> “熟悉 Agent”

对应：

> GitHub 项目 → 代码 → 技术证据。

### 6. Job Application Strategy

告诉用户：

> 今天应该投哪些岗位。

但这些全部属于后续版本。

---

# 三十、明确禁止做的事情

第一版禁止：

- 社交平台
- 聊天社区
- 在线课程
- 支付系统
- 企业账号
- 复杂权限系统
- 手机 App
- 微信小程序
- 10 万级爬虫
- 破解招聘网站反爬
- 自动投递职位
- 自动联系 HR
- 自动群发消息

这些都会严重稀释项目。

---

# 三十一、GitHub 开源质量要求

最终项目必须像一个真正的 GitHub 项目。

需要：

```text
README.md
ARCHITECTURE.md
DESIGN_DECISIONS.md
EVALUATION.md
DATA.md
API.md
DEVELOPMENT.md
```

README 必须包含：

> Problem

> Solution

> Architecture

> Demo

> Evaluation

> Limitations

> Roadmap

不要写成营销文案。

---

# 三十二、必须有 Design Decisions

建立：

```text
docs/adr/
```

至少记录：

### ADR-001

为什么 PostgreSQL + pgvector？

### ADR-002

为什么 deterministic scoring + LLM explanation？

### ADR-003

为什么 Skill Extraction 使用 Structured Output？

### ADR-004

为什么不直接依赖招聘网站爬虫？

### ADR-005

为什么 Agent 使用 LangGraph？

每一个设计决策都必须说明：

> Alternatives

> Pros

> Cons

> Decision

---

# 三十三、开发方式

严格采用：

> **Plan → Implement → Test → Review**

每完成一个阶段：

1. 自动运行测试
2. 检查代码质量
3. 检查架构
4. 检查是否偏离需求
5. Review 自己写的代码
6. 修复问题
7. 更新文档

不要一次生成整个项目。

---

# 三十四、开发阶段

最终先规划：

## Phase 0

市场研究 + 竞品研究 + GitHub 研究

## Phase 1

需求冻结 + Architecture

## Phase 2

数据模型 + Demo Dataset

## Phase 3

JD Analyzer + Skill Extraction

## Phase 4

Market Intelligence

## Phase 5

Candidate Profile

## Phase 6

Skill Gap

## Phase 7

Job Matching

## Phase 8

Recommendation Agent

## Phase 9

Evaluation

## Phase 10

Dashboard

## Phase 11

Docker + CI + Documentation

具体阶段可以根据研究结果调整。

---

# 三十五、每个阶段结束后必须自我 Review

Review：

### Product

这个功能真的解决问题吗？

### Engineering

架构是否过度设计？

### AI

LLM 是否被滥用？

### Data

数据是否真实？

### Evaluation

结果是否可验证？

### Resume

这个阶段是否产生真正值得写进简历的能力？

---

# 三十六、最终目标

我不是为了得到一个：

> “功能很多的 AI 网站”。

我要得到：

> **一个有真实问题、真实数据、明确技术难点、可解释决策、可验证 Evaluation、工程化完整、GitHub 可展示的 AI 应用项目。**

最终我希望面试官问：

> “为什么这么设计？”

我能够回答：

> **因为真实数据和实验结果证明这样更合理。**

而不是：

> “因为 Codex 这么写的。”

---

# 三十七、现在第一步

**不要写代码。**

先进行：

### 1. 当前 2026 AI 应用开发岗位市场研究

### 2. 牛客相关岗位 / 面经 / 项目讨论研究

### 3. GitHub 同类开源项目研究

### 4. 同类 AI 求职产品研究

### 5. 提取真实岗位技能频率

### 6. 找出市场真正缺口

### 7. 判断 JobLens 是否值得做

### 8. 找出至少 3 个可以形成差异化的功能

### 9. 给出 MVP

### 10. 给出完整技术架构

### 11. 给出数据库 Schema

### 12. 给出 Evaluation 方案

### 13. 给出开发 Roadmap

### 14. 给出 GitHub 项目参考

---

# 最终输出

创建：

```text
docs/
├── MARKET_RESEARCH.md
├── COMPETITOR_ANALYSIS.md
├── OPEN_SOURCE_RESEARCH.md
├── PRODUCT_SPEC.md
├── MVP.md
├── ARCHITECTURE.md
├── DATA_MODEL.md
├── EVALUATION_PLAN.md
├── DESIGN_DECISIONS.md
└── ROADMAP.md
```

---

# 最重要的要求

**不要因为我提出了一个想法，就默认这个想法一定正确。**

如果你的市场研究发现：

> JobLens 这个方向已经严重同质化

必须告诉我。

如果发现：

> 某个功能没有真实需求

删掉。

如果发现：

> 有另一个更前卫、更有就业价值的方向

可以推翻我的方案。

如果发现：

> 某项技术只是为了写进简历

不要使用。

你的目标不是：

> **帮我做一个看起来很牛的项目。**

而是：

> **帮我找到一个真实存在的问题，用工程和 AI 把它解决，并且让这个项目能够经得起真实用户、数据和技术面试官的检验。**

**先研究，后设计；先验证，后开发。**

现在开始 Phase 0。

不要写代码。
