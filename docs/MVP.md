# MVP —— 最小可行产品定义（Phase 1 冻结版）

> SkillGap Agent ｜ Phase 1 交付物 ｜ 本版替代 Phase 0 版本（变更记录见 DECISION_LOG.md D-2026-08-31-02）
> 一句话：**用户粘贴简历与目标 JD，系统输出证据化技能画像、可解释匹配分、分市场（中国/全球）的技能频率统计、技能缺口与"下一步最该学什么"的 ROI 优先级——每个数字可溯源，样本不足时明示。**

---

## 1. MVP 核心闭环（冻结）

```
User
 ↓ Paste Resume / JD
JD Analysis（LLM Structured Output）
 ↓
Skill Extraction → Skill Normalization（Taxonomy 归一）
 ↓
Candidate Profile（证据 + 置信度，确定性规则）
 ↓
Job Matching（确定性分数：Coverage / Importance / Evidence / Experience）
 ↓
Skill Gap（缺口 + transferable/genuine 区分）
 ↓
Recommendation（ROI 公式 → Priority 1/2/3）
 ↓
Evidence（每个结论回链 JD 原文 / 简历证据 / 统计快照）
```

Market Intelligence 与用户贡献 JD 通道并行运行，为闭环提供数据根基，受数据质量门禁约束（§4）。

---

## 2. MoSCoW 范围（Phase 1 冻结）

### 2.1 Must Have（第一版必须实现）

| # | 功能 | 最小形态 | 验收标准 |
|---|---|---|---|
| M1 | JD Analyzer | 粘贴单个 JD → 结构化输出（岗位/核心技能/次要技能/软性要求，每技能带原文证据片段） | Schema 校验通过率 ≥95%（评测集）；失败明示不静默 |
| M2 | Skill Extraction + Normalization | LLM Structured Output → alias 归一 → 证据可溯校验 | E1 F1 ≥0.75（Warn 线起步冲 0.85）；证据可溯率 100% |
| M3 | 用户贡献 JD（中国数据主通道） | JD 分析完成后 opt-in 匿名贡献：PII 检测/脱敏 → content_hash 去重 → 质量校验 → 入市场数据集 | PII 规则全覆盖（DATA_GOVERNANCE §4 清单）；去重准确；贡献状态与数据来源透明可查 |
| M4 | 数据导入与海外 Ingest | CSV/JSON 导入器（校验+去重+导入报告）；Adzuna 公开 API 连接器（用户自行运行，Global Market 专用） | 一条命令完成导入/拉取；导入报告含新增/重复/失败计数；Adzuna 数据仅进 Global 市场 |
| M5 | Candidate Profile | 简历粘贴 → 证据化画像（每技能：证据片段 + confidence，规则计算） | 每技能输出证据 + confidence；公式单测全覆盖（含"了解 MCP"→低分边界） |
| M6 | Job Matching | 确定性四项分数 + Strong/Weak/Missing + 分项解释 | 分数 100% 由公式计算（LLM 禁入）；每个数字有 evidence_ref；解释文本数字与 breakdown 程序比对一致 |
| M7 | Skill Gap | 岗位要求 vs 画像：缺口清单 + transferable/genuine 区分 | 能力提升→缺口单调收窄（纯函数单测）；完全无关/完全达标边界用例通过 |
| M8 | Market Intelligence | 分市场（China/Global）技能频率统计 + 样本量 + 来源分布 + 溯源 | 每个百分比附 N、窗口、来源分布、置信度分级；N<阈值输出"样本不足"；两市场永不混算 |
| M9 | Recommendation | ROI 公式（Demand×Gap÷Cost）→ Priority 1/2/3 + 项目建议 | 数值 100% 公式计算；解释引用真实频率数据；LLM 不产生任何数字 |
| M10 | Dashboard | 六视图：画像/雷达/热门技能/缺口/ROI 建议/匹配解释 | 数据全部来自 API（无前端硬编码）；样本量守门在 UI 呈现 |
| M11 | Evaluation 基础 | E1 标注集（50-100 JD）+ E5 数据质量指标 + CI 门禁 | 评测可复现、进版本历史；数据质量指标每次导入后产出报告 |

### 2.2 Should Have（重要但可后置）

| 功能 | 说明 | 触发条件 |
|---|---|---|
| 市场趋势（7/30/90 天） | MarketSnapshot 时间序列对比 | 数据积累：目标切片 N≥100 且时间跨度 ≥30 天 |
| 项目推荐模板库 | 缺口技能 × 项目模板（人工策划，标注来源） | M9 稳定 + 模板 ≥5 个 |
| PDF 简历解析 | 文件上传通道（v1 文本粘贴已闭环） | 文本通道验证后 |
| E2/E3 完整评测 | 匹配标注集 20-30 对 + 推荐排序评测 | Phase 7/8 对应阶段建设 |
| 数据质量报告页 | Duplicate/Missing/PII/Invalid/Error 五指标可视化 | M11 指标落地后加 UI |
| 解释生成完善 | LLM 解释模板迭代（含对比基线 Huntr 四维可解释性自查） | Phase 7 |

### 2.3 Could Have（未来增强）

| 功能 | 说明 |
|---|---|
| RAG 知识问答 | "为什么推荐我学 MCP"→ 检索 JD 数据/频率口径生成带引用回答（pgvector 按需启用） |
| GitHub 仓库证据（方式 D） | README/语言/依赖/commit 结构分析，"声明 vs 代码证明"对比 |
| Career Planner Agent | LangGraph 单 Agent 编排个性化决策（ADR-006 复议点） |
| MCP Server 形态 | 把 SkillGap Agent 变成 AI IDE 的技能顾问工具 |
| Remotive 等补充海外源 | 条款核查通过后的增量连接器 |

### 2.4 Won't Have（明确不做——含永久红线）

| 项 | 理由 |
|---|---|
| **任何招聘平台爬虫（BOSS 直聘/牛客/拉勾/智联/猎聘）** | **项目硬约束**（ADR-001），非可协商项 |
| 绕过登录/验证码/反爬、模拟用户行为批量采集 | 同上，合法性优先于数据规模 |
| USAJOBS 等条款禁止聚合使用的数据源 | 条款核查结论：禁止衍生作品/聚合交付（DATA_GOVERNANCE §6） |
| LLM 生成统计数字 / Match Score / ROI 数值 | ADR-005 三层分离红线 |
| 海外数据冒充中国市场统计 | 市场分离硬约束（ADR-002 附则） |
| 账号体系/多租户 SaaS/复杂权限 | 单用户本地场景足够；YAGNI |
| 自动投递、联系 HR、群发消息、Job Tracker | Phase 0 禁止清单延续 |
| 聊天框为主的产品形态 | 产品定位是数据与决策展示 |
| 面试模拟、在线课程、社交社区 | Phase 0 禁止清单延续 |

---

## 3. 数据策略（差异化根基）

```
数据来源（三通道 + Trust Model）：
 ① Public API（Tier A）        Adzuna（免费层，Global Market 专用，用户自行运行 ingest）
 ② Public Job Page（Tier A）   公司官方招聘页人工摘录（记录 source_url）
 ③ User Submitted JD（Tier B）  用户主动粘贴 + opt-in 匿名贡献（中国市场主通道）
 ＋ CSV/JSON 导入（Tier C）     社区批量贡献
 （远期候选：Remotive 等条款核查通过源；USAJOBS 已排除）

市场分离：
 · China Market   = 用户提交 JD + 中文公开页面摘录（中文为主）
 · Global Market  = Adzuna 等海外公开 API（英文为主）
 · 统计永远按 market 维度分开输出，禁止混算

收集纪律：
 · 每条 JD 记录：source_type / source_name / source_url / collected_at /
   submitted_at / content_hash / license_or_usage_note / consent_status / data_quality
 · 用户贡献数据入库前必过 PII 检测 + 脱敏（DATA_GOVERNANCE §4）
 · 样本量分级：N≥200 High ｜ 50≤N<200 Medium ｜ 30≤N<50 Low ｜ N<30 不出统计
```

**中国 Demo Dataset 构建成本估算**：200 条 × 约 3 分钟/条（人工在公开招聘页浏览→复制→记录来源）≈ 10 小时，分 4-5 批，每批 50 条后跑频率统计校准词表。

---

## 4. 数据质量门禁（Data Quality Gates）

每道门禁在 DATA_PIPELINE.md 中有对应步骤与失败处置；指标进 E5 评测（EVALUATION_PLAN §6）。

| 门禁 | 位置 | 规则 | 违规处置 |
|---|---|---|---|
| G1 去重门禁 | Dedup 步骤 | content_hash 唯一索引；同 hash 拒绝 | 拒绝入库，计入 duplicate_count |
| G2 完整性门禁 | 入库前 | 来源九字段完整（见 §3）；public_job_page 必须有 source_url | 拒绝入库 → quarantine 队列 |
| G3 PII 门禁 | 入库前 | 用户贡献 JD 必过 PII 扫描；命中项替换为标记 | 未处理数据永不进入 market dataset |
| G4 有效性门禁 | Validation 步骤 | JD 长度 50-20000 字符；语言可识别；岗位类别可判定 | 隔离（quarantine），人工复核后放行或丢弃 |
| G5 抽取门禁 | Skill Extraction 后 | Schema 校验失败重试 ≤2 次，仍失败标记 extraction_failed | 不进统计，进入错误率报告 |
| G6 统计守门 | Market Analytics | 切片 N<30 不出统计；所有统计附样本量/窗口/来源分布/置信度 | 强制返回"样本不足"，禁止静默输出 |

---

## 5. MVP 成功标准

| 维度 | 标准 |
|---|---|
| 产品 | 完整闭环可走通（粘贴→画像→匹配→频率→缺口→建议），全程无 LLM 黑盒数字 |
| 工程 | clone → docker compose → import → run 一条命令；pytest + GitHub Actions CI 全绿 |
| 数据 | 中国市场：200+ 条 JD 来源透明；全球市场：Adzuna 首批拉取入库且 attribution 到位；频率统计可复现 |
| 评估 | E1 F1 ≥ 阈值；E5 五项数据质量指标有基线报告；结果进回归历史 |
| 简历价值 | 面试可答：数据从哪来（DATA_GOVERNANCE）、为什么这么设计（ADR）、怎么证明有效（EVALUATION_PLAN） |

---

## 6. 风险与止损线

| 风险 | 触发信号 | 止损动作 |
|---|---|---|
| 中国数据集积累不及预期 | 2 周内 <100 条 | 缩小岗位范围（只做"AI 应用开发"单一切片）保深度 |
| Adzuna 免费额度/条款变动 | 连续超额或条款收紧 | Global 市场统计降频（周级快照），或暂停海外源只保留中国市场 |
| 技能抽取质量不达标 | F1 持续 <0.75 且迭代 3 轮无改善 | 缩小词表（保高频 15 技能高质量） |
| PII 漏检 | 抽查发现漏检 | 规则迭代 + 人工审核比例上调 |
| 范围蔓延 | 任何"顺手加个小功能"提议 | 引用 §2.4 冻结清单否决 |
