# COMPETITOR_ANALYSIS —— AI 求职产品竞品研究（Phase 0）

> SkillGap Agent Phase 0 交付物之一 ｜ 研究时间：2026-08-31
> 结论一句话：**"简历 vs JD 匹配"是同质化最严重的红海；无人完整覆盖"真实 JD 频率统计 → 证据化画像 → 技能缺口 → 学习优先级 → 可解释决策"闭环。**

---

## 0. 核实状态说明

- **[已核实]** = 已实际打开产品页面提取信息；**[线索]** = 仅来自搜索摘要，未打开核实。
- 企业端（Moka、招聘平台 B 端功能）与登录后功能无法完全验证，标注从简。

---

## 1. 竞品总表（规划文档要求格式）

### 1.1 AI 简历优化器

| 产品 | 解决的问题 | 核心功能 | 技术特点 | 优点 | 缺点 | 我们是否需要 |
|---|---|---|---|---|---|---|
| 超级简历 WonderCV [已核实] | 按 JD 定制中文简历 | 粘贴 JD→关键词分析→匹配度；关键词密度检测、措辞优化、ATS 校准 | 160 万字行业语料库 + 5000+ 专业表达模型 | 中文场景完整，用户能看到关键词缺失方向 | 无市场频率统计、无技能缺口排序、无学习优先级 | **不需要**复刻；仅保留"粘贴 JD→结构化分析"交互模式 |
| Huntr [已核实] | 简历定制 + 求职管理 | Job Match Score 四维评估（Qualifications/Responsibilities/Keywords/Job Title）；Must-Have/Nice-to-Have 权重；Covered/Not Covered 状态；语义匹配 | LLM 驱动加权评分 | **可解释性最强**：能看到覆盖项、缺失项、权重、原因 | 无市场层频率数据、无学习优先级、单 JD 视角 | **需要借鉴**：可解释匹配的呈现方式（四维分数+覆盖明细）是我们的下限，不是差异点 |
| Teal [线索] | 求职管理 | Match Score、关键词扫描、Job Tracker、AI bullet 生成 | 关键词对齐 + 求职追踪 | 求职管理闭环完整 | 无技能缺口决策、无市场数据 | 不需要 |
| Rezi [线索] | AI 简历构建 | AI resume tailor、关键词分析、ATS 适配、**MCP server**（接入 Claude/Cursor 等） | AI 改写 + MCP 工具连接 | 工具链完整、定价清晰 | 无市场频率、无优先级 | 不需要；MCP 接入思路值得记入远期候选 |
| Kickresume [线索] | 英文简历生成 | JD 关键词分析、AI 改写、ATS 检查、Career Map | AI 改写 | 英文场景成熟 | 无缺口分析 | 不需要 |
| Enhancv [线索] | 高设计感简历 | 模板、图表、AI 写作助手、ATS 检查 | 模板引擎 | 设计感强 | 无 JD 决策能力 | 不需要（明确避开模板美化方向） |

### 1.2 AI Job Matcher / 岗位推荐

| 产品 | 解决的问题 | 核心功能 | 技术特点 | 优点 | 缺点 | 我们是否需要 |
|---|---|---|---|---|---|---|
| LinkedIn [线索] | 职业推荐与匹配 | Job Match（资格对齐+竞争位置）、Economic Graph（38,000+ 技能图谱）、skill gap analysis | ML+NLP+经济图谱 | 技能图谱规模全球最大 | 求职者端解释有限、非中国主流渠道 | 需要**学习其技能图谱思想**（Skill Graph 数据结构），不做其规模 |
| Indeed [已核实] | 大规模人岗匹配 | AI matching engine、Career Scout（AI 职业教练）、匹配驱动 70% 赞助申请 | skills+experience+preferences+实时行为反馈，6.35 亿求职者画像 | 数据规模与反馈闭环业界顶级 | 无求职者端技能缺口解释、无学习优先级 | 不做规模；**反馈闭环思想**（用户行为回流改进推荐）记入远期 |
| BOSS直聘 [线索] | 中国直聊招聘 | 招聘端 AI Agent、南北阁大模型、DeepSeek 接入 | 自研大模型 + 平台数据 | 平台数据壁垒深 | 求职者端无可解释技能缺口 | 不需要（平台级竞争不可行） |
| 智联招聘 [线索] | 综合招聘 | AI 简历优化、求职侠 AI 工具、AI 推荐人才 | 千帆/千问/DeepSeek 接入 | 平台岗位数据 | 无缺口决策 | 不需要 |
| Moka [线索] | 企业端招聘 | AI 简历解析、语义匹配、Match Score Dashboard | Moka Eva 深度语义理解 | 企业端匹配可视化好 | 面向 HR 不面向求职者 | 不需要（我们是求职者侧） |

### 1.3 Career Advisor / 职业规划

| 产品 | 解决的问题 | 核心功能 | 技术特点 | 优点 | 缺点 | 我们是否需要 |
|---|---|---|---|---|---|---|
| Careerflow [已核实] | 求职 AI 助手 | LinkedIn 优化、AI 匹配、简历写作、JD summarizer、求职追踪 | AI 全流程工具 | 免费额度合理（10 个申请追踪） | 无市场数据驱动的技能决策 | 不需要 |
| LinkedIn Career Explorer [线索] | 技能迁移映射 | 技能→岗位迁移建议 | Economic Graph | 技能迁移视角独特 | 非实时市场频率 | 借鉴"技能迁移"概念（远期 What-if 功能） |
| Google Interview Warmup [线索] | 面试练习 | 行业问题生成、转录反馈 | 语音转写 | 免费、零门槛 | 反馈浅、无缺口分析 | 不需要 |

### 1.4 AI 面试/求职教练

| 产品 | 解决的问题 | 核心功能 | 技术特点 | 优点 | 缺点 | 我们是否需要 |
|---|---|---|---|---|---|---|
| 面试鸭/牛客 AI 面试 [线索] | 企业端 AI 面试 | 全岗位 AI 面试、智能追问、七维评估 | NowGPT 多模态 | 面试评估维度多 | 企业端产品，非求职者技能决策 | 不需要（方向不同） |
| Final Round AI [已核实] | 面试实时辅助 | Interview CoPilot、Prepare/Perform/Review、面试复盘 | 实时辅助 + 会话复盘 | 闭环完整、1000 万用户 | 无技能缺口、无市场数据 | 不需要 |
| OfferGoose [已核实] | 模拟面试 | AI mock interview、实时反馈、简历优化 | AI 面试 | 求职者侧 | 无缺口分析 | 不需要 |

### 1.5 求职技能学习平台

| 产品 | 解决的问题 | 核心功能 | 技术特点 | 优点 | 缺点 | 我们是否需要 |
|---|---|---|---|---|---|---|
| 牛客 [线索] | 技术求职学习 | 学习路线（Java/前端/Agent）、刷题、AI 面试 | 社区内容 | 国内技术求职社区覆盖最广 | 学习路线**非市场 JD 频率驱动**，静态人工编排 | **需要**：我们的推荐可以对接其路线内容（引用而非复刻） |
| LeetCode/CodeTop [线索] | 算法刷题 | 按知识点刷题、公司面试题频率统计 | 题库+统计 | **"考察频率统计"思想与 SkillGap Agent 同构** | 仅覆盖算法题，不覆盖技能全景 | 借鉴其"频率透明化"产品哲学 |
| DataCamp/Coursera [线索] | 技能学习 | 技能评估、技能报告 | 课程+测评 | AI literacy 增长数据 | 无个人 JD 驱动优先级 | 不需要 |

---

## 2. 竞争格局深度判断

### 2.1 市场空白（最大的机会）

**已核实与线索一致指向：无产品完整覆盖以下闭环——**

```
真实 JD 数据集 → 技能频率统计（可复现口径）
        ↓
用户证据化能力画像（声明 vs 证明，简历 + GitHub 代码证据）
        ↓
Skill Gap Analysis（可解释：每个缺口对应哪些 JD）
        ↓
学习/项目优先级推荐（需求 × 缺口 × 成本 → ROI，确定性计算）
        ↓
Evaluation（频率/匹配/推荐三层可验证）
```

各竞品只做其中一环：

- 超级简历/Rezi/Teal/Kickresume：停留在"简历改写 + 关键词对齐"
- Huntr：把"可解释匹配"做到了较好水平，但**只有单 JD 视角，没有市场层**
- LinkedIn/Indeed：有市场层数据，但**不向求职者开放透明的频率统计与缺口优先级**
- 牛客/LeetCode：有学习内容，但**优先级是人工静态编排，非数据驱动**

### 2.2 同质化红线（SkillGap Agent 绝不能做进去的方向）

1. **简历模板/美化**（Enhancv、超级简历已充分覆盖，且与技能决策无关）
2. **泛 AI 聊天式求职建议**（"AI 判断你匹配度 78%"这类黑盒输出是行业默认做法，恰是我们要反的）
3. **再做一个"简历 vs 单个 JD 匹配分"**（Huntr 已做到可解释四维评分，单纯追赶无差异化）
4. **岗位聚合/自动投递**（平台级竞争 + 规划文档明令禁止）
5. **面试模拟**（Final Round/面试鸭已充分覆盖，与技能决策链路弱相关）

### 2.3 必须达到的竞争基线（下限，非差异点）

- 匹配可解释性 ≥ Huntr（四维分数 + Covered/Not Covered + 原因）
- JD 分析输出 ≥ 超级简历的结构化程度
- 建议可追溯性 = 我们独有（引用具体 JD + 频率口径）

---

## 3. SkillGap Agent 不应该做什么（明确清单）

**产品层禁止：**

- ❌ 简历一键改写 / 措辞优化 / 模板生成 —— 同质化红海，稀释定位
- ❌ 求职进度管理 / Job Tracker —— Teal/Careerflow 已覆盖，无技术深度
- ❌ 模拟面试 / 面试实时辅助 —— 已有成熟产品，与核心链路无关
- ❌ 岗位聚合搜索 / 自动投递 / 联系 HR —— 平台级竞争 + 法律风险，规划文档明令禁止
- ❌ 社交 / 社区 / 课程 / 支付 / 企业账号 / 复杂权限 —— 规划文档明令禁止
- ❌ LLM 直接拍数字（匹配度、ROI、频率）—— 违反项目第一设计原则

**数据层禁止：**

- ❌ 破解反爬 / 绕过登录 / 验证码 —— 规划文档明令禁止
- ❌ 引用培训机构口径数据 / 无口径的外部薪资数字 —— 研究已证明不可靠

---

## 4. 从竞品研究导出的差异化功能（≥3 个，全部有空白证据）

| # | 差异化功能 | 空白证据 | 竞品最接近者及其缺口 |
|---|---|---|---|
| 1 | **Market-verified Skill Frequency**：自建 JD 数据集 → 技能频率统计，全口径可复现（N、时间窗、来源分布），建议可追溯到具体 JD | 无任何已研究产品向求职者开放透明频率统计 | LinkedIn 有数据不开放；CSDN 小样本统计证明需求存在但无人产品化 |
| 2 | **Evidence-based Skill Profile**：区分"简历声明"与"代码证明"（GitHub 仓库结构/依赖/测试/CI 分析），每技能带 Confidence 分数与证据链 | Huntr 只做 JD 侧覆盖检查，不做候选人侧证据分级；牛客面经"死亡追问"证明市场需要证据 | 无直接竞品；最接近的是企业端背调，非求职者侧 |
| 3 | **Skill Investment ROI**：需求频率 × 缺口 × 学习成本 → 优先级排序，确定性计算，LLM 只负责解释 | 全部竞品的建议均为 LLM 直接生成或人工静态编排 | 牛客学习路线是人工编排；Careerflow 是 LLM 生成 |
| 4 | **三层 Evaluation 闭环**：抽取 P/R/F1 + 匹配相关性 + 推荐质量，人工标注基准 | 无任何竞品（包括开源项目）公开技能抽取/匹配的评测集 | （见 OPEN_SOURCE_RESEARCH.md，同样空白） |

---

## 5. 风险与反面判断（诚实评估）

| 风险 | 严重度 | 说明与对策 |
|---|---|---|
| 数据集冷启动 | **高** | 差异化完全建立在自有 JD 数据集上；若收集不到足够 JD（100-500 条），频率统计不成立。对策：MVP 明确"手动粘贴 JD 优先 + CSV 导入 + 少量公开合规数据源"，并把样本量门槛写进产品逻辑（不足则明示） |
| 可解释匹配不再是差异点 | 中 | Huntr 已做到四维可解释。对策：把可解释定位为基线，差异点上移到"市场层 + 证据层" |
| 用户付费意愿低 | 低（MVP 阶段不涉及） | 本项目目标是简历级作品而非商业化，风险可接受 |
| 平台级玩家降维 | 低-中 | LinkedIn/BOSS 若开放同等功能则差异化消失。对策：聚焦中文 AI 应用开发垂类 + 开源可复现，避开平台战场 |

---

## 参考来源

- 超级简历：https://www.wondercv.com/jobscan/index?JobToken=ka_mHb8 [已核实]
- Huntr：https://huntr.co [已核实]
- Indeed：https://www.indeed.com [已核实]
- Careerflow：https://www.careerflow.ai [已核实]
- Final Round AI：https://www.finalroundai.com [已核实]
- OfferGoose：https://blog.offergoose.com [已核实]
- Rezi：https://www.rezi.ai [线索]
- Teal：https://www.tealhq.com [线索]
- Kickresume：https://www.kickresume.com [线索]
- Enhancv：https://enhancv.com [线索]
- LinkedIn：https://www.linkedin.com [线索]
- ZipRecruiter：https://www.ziprecruiter.com [线索]
- BOSS直聘：https://www.zhipin.com [线索]
- 智联招聘：https://www.zhaopin.com [线索]
- 猎聘：https://www.liepin.com [线索]
- Moka：https://mokahr.com [线索]
- 牛客：https://www.nowcoder.com [线索]
- 面试鸭：https://hr.nowcoder.com [线索]
- Google Interview Warmup：https://grow.google/interview-warmup/ [线索]
- DataCamp：https://www.datacamp.com ；Coursera：https://www.coursera.org [线索]
