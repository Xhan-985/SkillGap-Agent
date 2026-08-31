# PRODUCT_SPEC —— SkillGap Agent 产品规格（Phase 1 冻结版）

> SkillGap Agent ｜ Phase 1 交付物 ｜ 本版在 Phase 0 基础上冻结数据源三通道架构、中国/全球市场分离与用户贡献 JD 机制（变更记录见 DECISION_LOG.md）
> 定位一句话：**SkillGap Agent 不是"又一个 AI 简历匹配工具"，而是一个基于真实 JD 数据的证据化技能决策系统：市场需要什么 → 我真的会什么 → 我缺什么 → 接下来做什么最值。**

---

## 1. 研究修正后的定位陈述

### 1.1 原始定位（规划文档）

> 市场需要什么 → 用户有什么 → 用户缺什么 → 哪些岗位值得投 → 接下来做什么最有价值

### 1.2 Phase 0 研究后的修正

| 维度 | 原假设 | 研究结论 | 修正 |
|---|---|---|---|
| 核心叙事 | 求职匹配 + 建议 | "简历 vs JD 匹配"是同质化红海（Huntr 已做到可解释四维评分） | 核心叙事上移为**技能决策**："先回答该学什么，再回答适合哪些岗位，最后回答为什么" |
| 差异化根基 | 功能组合 | 无竞品/开源项目做市场频率统计 + 证据化画像 + ROI 优先级 | 三大差异化支柱全部保留并强化 |
| 数据假设 | 技能频率可以研究得到 | 公开渠道无系统频率数据 | **自建数据集从功能变为根基**——它是产品价值、差异化护城河与 Evaluation 基准的三合一 |
| 匹配功能定位 | 核心功能 | Huntr/Teal 等已充分覆盖单 JD 匹配 | 匹配降级为**链路中的一环**（且必须超越 Huntr 可解释性基线） |
| GitHub 分析 | 方式 D 之一 | 无竞品做证据化画像 | 升级为核心差异点，但**v2 实现**（MVP 只做简历证据） |

### 1.3 一句话价值主张（面向用户）

> 你说你会 RAG——你的代码证明了吗？目标岗位里 68% 要求 RAG——这个数字来自哪 200 条 JD？你只有 7 天——为什么建议先补 FastAPI 而不是 LoRA？每个答案，SkillGap Agent 都能给你证据。

---

## 2. 目标用户

| 用户画像 | 描述 | 核心诉求 | SkillGap Agent 回答 |
|---|---|---|---|
| **P1：AI 方向求职学生/实习党（主用户）** | 计算机/软件工程本科-硕士，做过后端/算法项目，目标 AI 应用开发/Agent 开发岗 | "我知道 Python/RAG/Agent，但不知道市场要什么、我差多少、先补什么" | 核心闭环全命中（牛客面经证明该人群被"死亡追问"困扰，急需证据化自证） |
| P2：转 AI 方向的在职开发者 | Java/后端 1-3 年，想转入大模型应用 | "我的旧技能哪些可迁移、缺口在哪、多久能补" | Skill Gap + transferable 区分（JobBot 验证的 gap 分类有价值） |
| P3：项目展示场景（隐含用户=面试官） | 查看 SkillGap Agent 项目本身的招聘方 | 验证求职者工程能力 | 产品本身即证据（Evaluation 透明、架构决策文档化） |

**非目标用户**：HR/招聘方（Moka 等企业端已覆盖）、非技术岗求职者（技能词表不支持）、泛职业咨询需求者。

---

## 3. 核心用户流程（端到端闭环）

```
注册/本地用户
      ↓
[输入侧] 粘贴简历文本（MVP 主通道）或填写技能；上传 PDF 为 Should Have；输入 GitHub 仓库（v2）
      ↓
能力分析 → 证据化技能画像（每技能：证据 + 置信度）
      ↓
[市场侧] 粘贴目标 JD（主通道） / 导入 Demo Dataset 批量 JD / Adzuna 海外拉取（Global）
      ↓
JD 结构化分析（岗位/核心技能/次要技能/软性要求/薪资）
      ↓
（可选）匿名贡献到市场数据集（opt-in，PII 脱敏后）
      ↓
Market Intelligence（技能频率统计，标注样本量/置信度/来源分布，China/Global 分离）
      ↓
Skill Gap Analysis（岗位要求 vs 用户画像，星级差距）
      ↓
岗位匹配（Overall Match + Strong/Weak/Missing + 可解释依据）
      ↓
技能投资回报（需求 × 缺口 × 成本 → Potential Gain，确定性计算）
      ↓
优先级决策（Priority 1/2/3：先补什么、做什么项目）
      ↓
[输出] Dashboard：画像/雷达/热门技能/缺口/推荐学习/推荐项目
      ↓
用户反馈 + Evaluation → 持续优化
```

---

## 4. 功能规格

### F1 JD Analyzer（MVP）

- **输入**：用户粘贴单个 JD 文本（必须支持；数据源失效时的保底通道）
- **输出**（结构化 Schema）：
  - 岗位：标题、类别（映射到岗位词表）、城市、薪资区间
  - 核心技能（必须项，带重要度）
  - 次要技能（加分项）
  - 软性要求（沟通、学历、经验年限）
  - 证据：每项技能标注其在 JD 原文中的出处片段
- **质量要求**：输出必须通过 Schema 校验；抽取失败明示，不静默降级

### F2 Skill Extraction（MVP，核心引擎）

- **方法**：LLM Structured Output + Skill Taxonomy 归一化 + 校验，**禁止纯字符串关键词匹配**
- **Taxonomy 结构**：

```
Skill
 ├── skill_id（ESCO 锚点优先，垂直技能自建 ID）
 ├── Category（Agent Framework / Retrieval / Serving / Engineering / ...）
 ├── Alias（"LangGraph.js"→LangGraph；"检索增强"→RAG）
 ├── Related Skill（LangGraph → Agent Framework → Agent Development 层级）
 ├── Importance（JD 中的必须/加分）
 └── Evidence（JD 原文片段）
```

- **垂直技能词表初始集**（源自 MARKET_RESEARCH.md §2.3，须在自建数据集中验证频率后才进入统计输出）：Python、Java、RAG、LangChain、LangGraph、AutoGen、CrewAI、MCP、Dify、FastAPI、Docker、K8s、PostgreSQL、MySQL、Redis、pgvector、Milvus、Chroma、Qdrant、Prompt Engineering、SFT/LoRA、vLLM、Evaluation、多模态
- **中文处理要求**：程度词识别（精通/熟练/熟悉/了解）映射到要求强度

### F3 Job Market Intelligence（MVP）

- **输入**：累计 JD 数据集（中国市场：用户贡献 + 公开页面摘录 + Demo Dataset；全球市场：Adzuna 公开 API）
- **输出**：技能出现频率（%）、按岗位类别/城市/薪资段的切片统计——**永远按 market 维度分开输出（China / Global 两个独立视图，无合并视图）**
- **数据纪律（硬约束）**：
  - 每个统计输出必须附带：样本量 N、置信度分级（N≥200 High / 50-200 Medium / 30-50 Low / <30 不出统计）、数据窗口、来源分布（Tier A/B/C）
  - **样本量不足阈值时输出"当前样本量不足以判断趋势"**，禁止生成趋势结论
  - 统计一律 SQL/Python 计算，**禁止 LLM 参与统计**
  - **海外数据不得冒充中国市场统计**（DB 约束 + 服务层双保险）；Global 视图常驻 "Jobs by Adzuna" 归属标识

### F4 技能趋势（MVP 简版 → v2 完整）

- 数据量允许时输出 7/30/90 天技能变化（↑/→/↓）
- MVP 仅做数据结构预留（`collected_at` 字段 + 时间切片查询），不做趋势 UI——研究结论：初始数据集难有足够时间跨度，诚实优于功能

### F5 Candidate Profile（MVP：方式 B/C；Should Have：方式 A PDF；v2：方式 D GitHub）

- **方式 B（MVP 主通道）**：粘贴简历文本 ｜ **方式 C（MVP）**：手动勾选技能 ｜ **方式 A（Should Have，MVP.md §2.2）**：PDF 简历解析——文本通道验证后再加，不在 MVP 内（2026-08-31 评审 H7 修复：消除与 MoSCoW 的口径矛盾）
- **证据化输出**（核心差异点）：

```
Skill: RAG
Evidence: 项目 A（简历段落：pgvector + Hybrid Search + RRF + Rerank）
Confidence: 0.91   ← 有具体技术细节支撑
---
Skill: MCP
Evidence: 简历原文"了解 MCP"
Confidence: 0.45   ← 仅为声明，无细节
```

- **Confidence 计算规则（确定性）**：证据类型加权（具体技术细节 > 项目描述 > 裸声明；简历出现 1 次 vs 多次）
- **方式 D（v2）**：GitHub 仓库分析——README/languages/结构/commit 活动/依赖清单/测试/CI/文档，输出"声明 vs 代码证明"对比。**MVP 不做**（工程量大，且简历证据已可支撑闭环）

### F6 Skill Gap Analysis（MVP，核心）

- **输入**：目标岗位技能要求（重要度星级） + 用户画像（能力星级）
- **输出**：每技能差距（星级差） + **最大技能缺口清单**（按 ROI 排序，见 F7） + transferable/genuine 缺口区分
- 要求重要度 × 用户置信度同时呈现（差距 = 岗位重要度 vs 用户能力置信度）

### F7 Skill Investment ROI（MVP，核心创新）

- **输入**：用户时间预算（7/14/30 天）
- **计算模型（确定性，公式公开）**：

```
Potential Gain(技能 s) = Demand(s) × GapSeverity(s) ÷ LearningCost(s)
其中：
  Demand(s)     = 数据集中 s 的出现频率（可追溯到 N 条 JD）
  GapSeverity   = 岗位重要度星级 − 用户能力星级（clamp ≥ 0）
  LearningCost  = 技能表预置的学习成本分级（Low/Mid/High，人工标注并公开）
```

- **输出**：技能 | Demand | Gap | Cost | Potential Gain 四列表 + 优先级建议
- **红线**：Potential Gain 数字由公式计算，**LLM 不得修改数值，只负责把公式结果翻译成解释文本**

### F8 Job Matching（MVP）

- **输入**：用户画像 + 单个 JD
- **输出**：Overall Match（加权确定性分数）+ Strong/Weak/Missing 三组 + **逐项可解释依据**
- **基线要求**（竞品研究导出）：可解释性不低于 Huntr（四维分数 + Covered/Not Covered + 原因）；我们的加项 = 技能的 Evidence 链接
- 禁止输出"AI 判断你匹配度为 78%"——必须给出分项构成

### F9 Recommendation（MVP 简版 + v2 Agent）

- **Priority 1/2/3 建议**：补什么技能（依据 F7 ROI）→ 做什么项目（缺口技能 × 项目模板）→ 为什么（引用频率与缺口数据）
- **项目推荐模板**：如"MCP + RAG Knowledge Agent（2-3 天，证明技能：MCP/RAG/Tool Calling/Agent）"——项目库初期人工策划，标注"模板人工策划"（不冒充数据驱动）
- **v2**：Career Planner Agent 用 LangGraph 编排上述决策流（见 ARCHITECTURE.md 取舍分析）

### F10 RAG 知识问答（v2，可解释性用）

- 用途限定：回答"为什么推荐我学 MCP"时检索并引用：哪些具体 JD 要求 MCP + 频率口径
- **建议必须能追溯到真实数据**（引用 JD ID + 原文片段）

### F11 Dashboard（MVP）

核心视图：我的就业画像（技能星级 + 置信度）｜ Match Score ｜ 技能雷达 ｜ 市场热门技能（频率条形图，带样本量标注，China/Global 切换）｜ 我的技能缺口（ROI 排序）｜ 推荐学习/项目 ｜ 目标岗位。
**重点展示数据和决策，不是聊天框**（规划文档要求 + 竞品研究确认差异化）。页面规格见 UI_SPEC.md。

### F12 用户贡献 JD 通道（MVP，中国市场数据主通道）

- **机制**：JD 分析完成后询问"匿名贡献到市场数据集"（**默认不勾选，明确 opt-in**）——用户在 BOSS/牛客等招聘软件看到岗位后自行复制粘贴，是用户处置自己浏览内容的行为，与平台自动抓取完全不同（ADR-001/002）
- **管道**：PII 检测（正则）→ PII 脱敏（[PHONE_REDACTED] 等标记）→ content_hash 去重 → 质量校验 → 技能抽取 → 市场数据集（consent_status=market_analysis）
- **隐私**：匿名（不记贡献者身份）；一次性 deletion_code 支持删除；**不声称 100% 识别所有 PII**（规则 + 人工抽查 + quarantine 三层）
- **诚实展示**：贡献结果页显示 PII 命中摘要与去重状态——用户知道自己贡献了什么、系统处理了什么

---

## 5. 设计原则（全项目约束）

1. **Deterministic Layer + LLM Layer + Evidence Layer 三层分离**（ADR-005）
2. **LLM 只做四件事**：技能抽取（Structured Output）、解释生成、简历证据识别、（Phase 8）Agent 决策编排。**不做**：频率统计、分数计算、ROI 数值
3. **每个数字可追溯**：频率→JD 集合；置信度→证据链；ROI→公式（ADR-007）
4. **诚实降级**：数据不足 → 明示不足，不伪造；统计必附样本量（ADR-008）
5. **数据透明**：每条 JD 带来源九字段；市场统计分 China/Global 且附来源分布（ADR-002）
6. **禁止爬虫**：不开发任何针对招聘平台的自动化采集（ADR-001，项目红线）

---

## 6. 明确禁止清单（Phase 0 冻结）

**产品层**：社交平台、聊天社区、在线课程、支付、企业账号、复杂权限、手机 App、小程序、简历模板美化、Job Tracker、面试模拟、岗位聚合、自动投递、联系 HR、群发消息。
**数据层**：破解验证码、绕过登录/反爬、非法隐私数据、10 万级爬虫、引用无口径外部数据。

---

## 7. 开放问题决策记录（Phase 1 全部落定）

| # | 问题 | 决策 | 状态 |
|---|---|---|---|
| Q1 | 暂定名 JobLens 与 GitHub 上 3 个同名项目冲突 | **已决策（2026-08-31）：定名 SkillGap Agent**；原始需求文档保留于项目根目录，其中 JobLens 为暂定名 | ✅ 已解决 |
| Q2 | Demo Dataset 规模 | **已冻结（2026-08-31）**：中国市场 200-300 条中文 JD（人工收集 + 公开页面合规摘录 + 标注来源），支持 CSV/JSON 导入；另加 Adzuna 首批海外数据（Global 市场，按免费额度拉取） | ✅ 已解决 |
| Q3 | GitHub 分析（方式 D）是否进 MVP | **已冻结（2026-08-31）**：不进（v2），MVP 用简历证据闭环（MoSCoW Could Have） | ✅ 已解决 |
| Q4 | LLM Provider 首发选择 | **已冻结（2026-08-31）**：OpenAI-compatible 抽象 + 单一实现（如 DeepSeek），不并发多 Provider | ✅ 已解决 |
| Q5 | 海外数据源选型（Phase 1 新增） | **已核查（2026-08-31）**：Adzuna 采用（Tier A，Global 专用，遵守 attribution 与免费额度）；Remotive 备选；USAJOBS 排除（条款禁止聚合）；Greenhouse/Lever 暂缓（无官方条款页）。核查结论见 DATA_GOVERNANCE §6 | ✅ 已解决 |
