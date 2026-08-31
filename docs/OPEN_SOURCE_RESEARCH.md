# OPEN_SOURCE_RESEARCH —— GitHub 开源项目研究（Phase 0）

> SkillGap Agent Phase 0 交付物之一 ｜ 研究时间：2026-08-31
> 结论一句话：**没有任何开源项目覆盖"技能抽取 → 市场频率 → 证据化画像 → Skill Gap → 优先级推荐 → Evaluation"完整链路；GitHub 上存在 3 个与暂定名 JobLens 同名的项目——已决议定名 SkillGap Agent。**

---

## 0. 核实状态说明

- **[已核实]** = 已实际打开 GitHub 仓库页面；**[摘要]** = 仅搜索摘要，未打开。
- GitHub 页面抓取不显示 Star 数的，标注"未显示"，不猜测。

---

## ⚠️ 1. 命名冲突（已解决：定名 SkillGap Agent）

调研发现 GitHub 上已存在多个同名/近似名项目：

| 仓库 | 定位 | 状态 |
|---|---|---|
| rpss30/JobLens-AI | 求职匹配/岗位分析，Streamlit+Django+PostgreSQL+Groq/Gemini，243 commits | [已核实] 活跃 |
| JEbertowski/JobLens | AI Resume Optimizer，Flask+React+OpenAI，ATS-style match scoring，已部署 | [已核实] |
| subham-sharma21/JobLens | Job Market Intelligence Platform，FastAPI+PostgreSQL，最近提交 2026-01 | [已核实] |
| rohith-jpg/joblens-mcp | MCP server：Adzuna 岗位搜索 + 简历解析 + 匹配打分 | [已核实] |

**影响与建议**：
1. 项目定位与上述项目高度重叠（尤其 subham-sharma21/JobLens 同为"Job Market Intelligence"），搜索引擎/GitHub 检索会直接撞车。
2. "不要假装我们是第一个"是规划文档的明确要求——上述项目证明这个方向已有尝试者，但**均为个人项目规模（commits 量级 2~243，无一个是社区主流项目）**，没有形成事实标准。
3. **决议（2026-08-31）**：放弃暂定名 JobLens，**定名 `SkillGap Agent`**，避免与上述同名项目在搜索与 GitHub 检索中撞车。原始需求文档（项目根目录 `JobLens_Codex_项目规划提示词.md`）中的 "JobLens" 一律视为暂定名；README 无需再写差异声明，但差异化论述必须成立。

---

## 2. A 类：Job/Career 开源项目（14 个，重点）

### 2.1 完整链路覆盖矩阵

```
项目                技能抽取  市场频率  证据画像  Skill Gap  匹配  优先级推荐  Evaluation
─────────────────────────────────────────────────────────────────────────────────
Resume-Matcher        △         ✗        ✗        ✗        △      ✗          ✗
JobMatch              ✗         ✗        ✗        ✓        ✓      △          ✗
ResumeRadar           ✓         ✗        ✗        ✗        ✗      ✗          ✗
JobBot                △         ✗        ✗        ✓        ✗      ✗          ✗
CareerScope AI        △         ✗        ✗        ✓        ✓      ✗          ✗
Resume_Screening_Ai   ✓         ✗        ✗        ✓        ✓      △          ✗
JobLens-AI 等4个      △         ✗        ✗        ✗        ✓      ✗          ✗
─────────────────────────────────────────────────────────────────────────────────
SkillGap Agent（我们）       ✓         ✓        ✓        ✓        ✓      ✓          ✓
```

**结论：完整链路的每一环都有人做过，但没有人串起来，且没有任何项目做"真实市场频率统计"与"证据化画像"。**

### 2.2 重点项目逐一分析

#### Resume-Matcher（srbhr）[已核实]
- **URL**：https://github.com/srbhr/Resume-Matcher ｜ 1,456 commits，最近提交 2026-07，**本领域最活跃项目**
- **解决**：开源 AI 简历优化，简历 vs JD 对比排序与改进建议
- **架构**：FastAPI + Next.js + LiteLLM（多 provider 含 Ollama 本地）；技能提取、requirements 提取、文本相似匹配
- **值得借鉴**：LiteLLM 式多 Provider 抽象；技能提取 + requirements 提取的分离
- **不足**：偏简历优化视角；无市场频率、无优先级、无 Evaluation

#### JobMatch（shivam-010303）[已核实]
- **URL**：https://github.com/shivam-010303/JobMatch ｜ 8 commits
- **解决**：Tech Job Recommender
- **架构**：Streamlit + FastAPI + SQLite + Sentence-Transformers + Qdrant + Groq/Llama3；**5 维加权评分（skills/experience/seniority/location/salary）** + LLM 生成推荐理由 + Skill Gap 分析 + Feedback API
- **值得借鉴**：**确定性加权评分 + LLM 解释**的两层结构（与我们设计原则完全一致，互相印证）；Feedback API 的评估数据收集意识
- **不足**：Skill Gap 仅用于解释展示，无优先级排序与 ROI；无市场频率

#### ResumeRadar（anujott-codes）[已核实]
- **URL**：https://github.com/anujott-codes/ResumeRadar ｜ 34 commits
- **解决**：简历与 JD 的技能实体抽取
- **架构**：NER 模型 + curated hard-skills 白名单 + 技能分类 + dense encoding；含 training 目录
- **值得借鉴**：**"模型抽取 + 白名单归一化"的混合抽取思路**；可复现的训练目录结构
- **不足**：无市场层、无评估闭环

#### JobBot（shruthi-hariprasad）[已核实]
- **URL**：https://github.com/shruthi-hariprasad/jobbot ｜ 6 commits
- **解决**：JD 技能 vs 简历匹配 + 优先化 gap 报告
- **架构**：LangGraph/LangChain agent；**ESCO 技能体系**；gap 分 critical/minor；coverage score；区分 transferable gap 与 genuine gap
- **值得借鉴**：**ESCO 标准技能 ID 作为归一化锚点**（防止 LangChain/LangChain.js 被当成两个技能）；transferable vs genuine gap 的区分
- **不足**：个人项目规模；无市场频率、无 Evaluation

#### CareerScope AI（KonQcs）[已核实]
- **URL**：https://github.com/KonQcs/CareerScope_AI ｜ 16 commits
- **解决**：CV/Portfolio 与 Job-Market 匹配平台
- **架构**：FastAPI + Streamlit + SQLite/PostgreSQL + Docker Compose + GitHub Actions + pytest；skill-gap、**可解释匹配（component-level scores）**、排序推荐、市场分析 dashboard、Adzuna API 适配、OpenAI 解释层
- **值得借鉴**：**工程化最完整**（CI+测试+Docker），架构与技术栈与 SkillGap Agent 规划几乎一致——证明技术选型合理，也证明"仅做到这一步"不够
- **不足**：无真实市场频率统计、无证据化画像、无 Evaluation

#### Resume_Screening_Ai（ayush42patel）[已核实]
- **URL**：https://github.com/ayush42patel/Resume_Screening_Ai ｜ 14 commits
- **解决**：ATS 模拟 + 职业助手
- **架构**：Streamlit + TF-IDF + FAISS + PDFPlumber；**Kaggle LinkedIn Job Postings Dataset**；ATS 分 + missing skills + 项目建议 + 学习路线
- **值得借鉴**：**用公开 Kaggle 数据集解决冷启动**；"项目建议 + 学习路线"输出形态
- **不足**：TF-IDF 语义能力弱；无 Evaluation

#### 其余项目（简表）

| 项目 | 亮点 | 关键不足 |
|---|---|---|
| JobLens-AI（rpss30）[已核实] | 工程栈完整（Terraform/ECS/Docker） | 无差异化功能展开 |
| JobLens（JEbertowski）[已核实] | 已部署有 Demo，CI/CD | 偏简历优化 |
| JobLens（subham-sharma21）[已核实] | FastAPI+PostgreSQL 数据目录 | 功能浅 |
| joblens-mcp（rohith-jpg）[已核实] | **Adzuna 官方 API 规避爬虫**；skill-overlap 分数透明 | 无市场层 |
| Resume Parser（bhavesh-nlp）[已核实] | 隐私优先设计；explainable scoring（skill score+semantic score 分离） | LLM 抽取列为 future scope |
| CareerRecommendationSystem [已核实] | 模块化 | 基于 curated profiles，非真实市场 |
| AI-Powered Skill Gap Analysis [已核实] | NLP+DSSM+向量库+简历解析的研究型完整思路 | 无市场频率、无评估 |
| ai-resume-analyzer-ats-system [已核实] | Match Score + Missing Skills 输出清晰 | TF-IDF 级别 |

---

## 3. B 类：AI 技术栈参考项目（架构参考，非竞品）

| 项目 | 对 SkillGap Agent 的用途 | 核实状态 |
|---|---|---|
| RAGAS（explodinggradients/ragas） | RAG 评估指标设计参考（Faithfulness、Context Recall/Precision 等）——用于"为什么推荐 X"的解释质量评估 | 摘要 |
| DeepEval（confident-ai/deepeval） | LLM-as-judge + 可解释调试；比 RAGAS 更偏开发者体验 | 摘要 |
| Promptfoo（promptfoo/promptfoo） | 规则式评估 + CI 集成，适合接入 GitHub Actions 做 Prompt 回归 | 摘要 |
| Awesome-Langgraph-Learn（GalaxyXieyu） | LangGraph 可运行示例：记忆（Redis）、多 agent handoff、Celery 异步 | 摘要 |
| structured-output-extractor（AhrendsW） | Pydantic/JSON Schema 验证 LLM 输出的实践参考 | 摘要 |

**启示**：评估框架（RAGAS/DeepEval/Promptfoo）是通用工具，SkillGap Agent 需要**领域专属评估集**（JD 技能抽取标注集、匹配打分集）——工具可借用，标注必须自建，这本身是差异化资产。

---

## 4. C 类：数据与分类体系（解决冷启动的关键发现）

| 项目 | 内容 | 对 SkillGap Agent 的价值 | 核实状态 |
|---|---|---|---|
| Open-Jobs（elliottdehn） | **约 96.7 万条当前开放岗位，Parquet 单文件，来自 16 个 ATS，LLM 提取结构化字段+预计算 embeddings，CC0 协议** | 合法合规的英文 JD 数据源；CC0 允许二次利用 | 摘要 |
| Open-Apply（edwarddgao） | 每日 06:00 UTC 从 Greenhouse/Lever/Ashby 公开 ATS API 刷新岗位数据集（HuggingFace） | **合法可持续数据源范式**：官方 ATS API 而非爬虫 | 摘要 |
| ESCO / O*NET（future-of-work-data、onet-feor 等） | 欧盟/美国官方技能与职业分类体系 | Skill Taxonomy 的标准锚点（技能 ID、别名、层级） | 摘要 |
| openhr-founder-ai skill-taxonomy | 对比 ESCO/O*NET/LinkedIn Skills Graph，建议以 ESCO 为基底的混合 taxonomy | Taxonomy 设计方法论参考 | 摘要 |
| Adzuna API | joblens-mcp 所用官方岗位 API | 备选合法数据源（覆盖有限） | 已核实（经项目页） |

**关键判断**：
1. **"合法数据源"问题已有成熟解法**：Greenhouse/Lever/Ashby 的公开 ATS API + Adzuna 官方 API + CC0 数据集（Open-Jobs）——完全避开爬虫与反爬，符合规划文档红线。局限：英文岗位为主，中文 JD 仍需手动收集/粘贴。
2. **Skill Taxonomy 不应从零发明**：以 ESCO/O*NET 为骨架 + 自建"AI 应用开发垂直技能表"（LangGraph/MCP/Dify 等新技能 ESCO 尚未收录），既有权威性又补市场新鲜度。

---

## 5. D 类：中文同类项目

本次检索未发现可核实的中文 JD 分析/技能缺口开源项目页面 [摘要]。
**判断**：中文场景（中文 JD、中文简历、国内技能词表如"精通/熟悉/了解"程度词）存在明显空白，且中文 NER/程度词处理有真实技术难度——这是差异化护城河的一部分，但也意味着无法借鉴现成方案，标注集必须完全自建。

---

## 6. 综合结论

### 6.1 "我们能不能做得更好？"——逐项回答规划文档的问题

| 问题 | 回答 |
|---|---|
| 它们解决了什么问题？ | 单点：简历优化（Resume-Matcher）、岗位推荐（JobMatch）、技能抽取（ResumeRadar）、gap 报告（JobBot） |
| 什么架构？ | 与我们规划同构：FastAPI+PostgreSQL+LLM 抽取+加权评分+LLM 解释——**选型被广泛验证，但天花板也清晰可见** |
| 哪些设计值得借鉴？ | LiteLLM 多 Provider；白名单+模型混合抽取；ESCO 技能 ID 归一；5 维确定性加权+LLM 解释；ATS API 合法数据源；pytest+CI+Docker 工程化 |
| 哪些设计明显不足？ | **无市场频率统计、无证据化画像、无 ROI 优先级、无 Evaluation**——四个维度全军覆没 |
| 我们能不能做得更好？ | **能**：完整链路 + 中文垂直场景 + 三层 Evaluation 是明确空白；但必须诚实——单点功能上我们大概率不超过最活跃的 Resume-Matcher，我们的价值在"链路完整 + 数据真实 + 可验证" |

### 6.2 对架构与数据决策的直接输入

1. Provider 抽象采用 OpenAI-compatible 接口模式（多项目验证）
2. 技能抽取 = LLM Structured Output + ESCO/白名单归一化 + 校验（ResumeRadar + JobBot 验证）
3. 匹配 = 确定性加权评分，LLM 只解释（JobMatch 验证）
4. 数据冷启动 = 手动粘贴 + CSV 导入为主，远期可评估 Open-Jobs/Open-Apply/Adzuna 作为英文补充（合法）
5. 工程化基线 = pytest + GitHub Actions + Docker Compose（CareerScope AI 验证为可行且必要）

---

## 参考来源

- https://github.com/srbhr/Resume-Matcher [已核实]
- https://github.com/shivam-010303/JobMatch [已核实]
- https://github.com/anujott-codes/ResumeRadar [已核实]
- https://github.com/shruthi-hariprasad/jobbot [已核实]
- https://github.com/KonQcs/CareerScope_AI [已核实]
- https://github.com/ayush42patel/Resume_Screening_Ai [已核实]
- https://github.com/rpss30/JobLens-AI [已核实]
- https://github.com/JEbertowski/JobLens [已核实]
- https://github.com/subham-sharma21/JobLens [已核实]
- https://github.com/rohith-jpg/joblens-mcp [已核实]
- https://github.com/bhavesh-nlp/resume-parser [已核实]
- https://github.com/abhinavxjha/CareerRecommendationSystem [已核实]
- https://github.com/sUhAs1011/AI_POWERED_SKILL_GAP_ANALYSIS_RESKILLING_FOR_EMPLOYMENT_TRENDS [已核实]
- https://github.com/adhipatya3552/ai-resume-analyzer-ats-system [已核实]
- https://github.com/explodinggradients/ragas [摘要]
- https://github.com/confident-ai/deepeval [摘要]
- https://github.com/promptfoo/promptfoo [摘要]
- https://github.com/GalaxyXieyu/Awesome-Langgraph-Learn [摘要]
- https://github.com/AhrendsW/structured-output-extractor [摘要]
- https://github.com/elliottdehn/open-jobs [摘要]
- https://github.com/edwarddgao/openapply [摘要]
- https://github.com/victoriano/future-of-work-data [摘要]
- https://github.com/martinneubrandt/onet-feor [摘要]
- https://github.com/ArjunFrancis/openhr-founder-ai/blob/main/docs/research/skill-taxonomy.md [摘要]
