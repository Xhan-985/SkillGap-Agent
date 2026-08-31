# ROADMAP —— 开发路线图（Phase 1 更新版）

> SkillGap Agent ｜ Phase 1 交付物更新
> 节奏：**Plan → Implement → Test → Review**，每阶段结束执行规划文档第三十五节的六维自检（Product/Engineering/AI/Data/Evaluation/Resume），通过后才进入下一阶段。不一次生成整个项目。

---

## 阶段总览

```
Phase 0  市场与竞品研究          【已完成 ✅】
Phase 1  需求冻结 + Architecture 【已完成 ✅（本次）】
Phase 2  数据模型落地 + 数据管道 + Demo Dataset
Phase 3  JD Analyzer + Skill Extraction
Phase 4  Market Intelligence
Phase 5  Candidate Profile
Phase 6  Skill Gap
Phase 7  Job Matching
Phase 8  Recommendation（Agent 引入）
Phase 9  Evaluation
Phase 10 Dashboard
Phase 11 Docker + CI + Documentation
```

研究结论对规划文档原阶段的调整：
1. **Evaluation 拆前不拆后**：E1（抽取评测）必须与 Phase 3 同步建设（抽取无评测=盲改），故 Phase 3 内含评测子环；Phase 9 做系统级汇总与 CI 门禁；**E5 数据质量评测随 Phase 2 数据管道同步建设**
2. **Demo Dataset 提前到 Phase 2**：数据是差异化根基（研究结论），且词表验证依赖数据；**数据管道与 Adzuna ingest 同期实现**（Phase 1 冻结的三通道架构）
3. **Phase 8 才引入 LangGraph**（ADR-006），Phase 1-7 无 Agent

---

## Phase 0：市场研究 + 竞品研究 + GitHub 研究 ✅（本次完成）

**产出**：本目录 10 份文档。
**结论**：值得做（完整链路空白 + 中文垂直空白），但核心叙事修正为"技能决策"，数据集是一切根基。命名已决议：**定名 SkillGap Agent**（原暂定名 JobLens，见 PRODUCT_SPEC §7 Q1）。

**进入 Phase 1 的前置条件（用户决策）**：
- [x] Q1 项目命名 → **已决策：定名 SkillGap Agent**（2026-08-31）
- [x] Q2 Demo Dataset 规模 → **已冻结：中国市场 200-300 条 + Adzuna 海外首批**（2026-08-31，PRODUCT_SPEC §7）
- [x] Q3 GitHub 分析不进 MVP → **已冻结：v2**（2026-08-31）
- [x] Q4 首发单一 Provider → **已冻结：OpenAI-compatible 单实现**（2026-08-31）

---

## Phase 1：需求冻结 + Architecture ✅（2026-08-31 完成）

| 项 | 内容 |
|---|---|
| 目标 | 冻结 MVP 范围（MoSCoW）、数据架构（三通道 + 市场分离）、API 契约、模块边界、数据治理、ADR 体系 |
| 产出 | **MVP.md**（MoSCoW + 数据质量门禁 G1-G6）｜ **DATA_PIPELINE.md**（S1-S12 分步规格）｜ **DATA_GOVERNANCE.md**（合规/PII/保留/API 条款核查）｜ **API.md**（16 端点契约）｜ **UI_SPEC.md**（7 页面）｜ **DECISION_LOG.md** ｜ **docs/adr/ADR-001~009**（DESIGN_DECISIONS.md 转索引）｜ 更新 PRODUCT_SPEC / DATA_MODEL / EVALUATION_PLAN（E5 数据质量）/ ARCHITECTURE（Ingestion Context）/ 本文件 ｜ **PHASE_1_REVIEW.md**（根目录，20 问自检 + 双角色评审报告，终判 PASS WITH RISKS） |
| 验收 | 需求文档第三十七节要求的文档清单 100% 齐备；每个 ADR 含 Context/Options/Pros/Cons/Decision；海外 API 条款核查完成（Adzuna 采用 / USAJOBS 排除 / Greenhouse/Lever 暂缓） |
| 完成状态 | ✅ 全部完成，**已停止等待用户确认后才进入 Phase 2**（需求第三十九节纪律） |

## Phase 2：数据模型落地 + 数据管道 + Demo Dataset

| 项 | 内容 |
|---|---|
| 目标 | 数据库落地 + 数据管道可用 + 内置数据集入库 |
| 产出 | PG Schema（含约束：来源九字段/content_hash 唯一/market 分离/status 过滤）；**Ingestion 管道实现（S1-S10：Adzuna 连接器 + CSV/JSON 导入器 + 用户贡献通道 + PII 规则库 + 去重 + 质检 quarantine）**；pgvector 预留表（不建索引）；**E5 数据质量指标实现（批次报告）**；**人工收集 200-300 条中文 JD**（分 4-5 批，每批 50 条后校准词表）；词表 v1 正式建档（skill/alias 表初版）；数据来源记录规范 |
| 验收 | 导入报告完整（新增/重复/失败计数）；PII 规则单测通过（含边界用例）；Adzuna 首批拉取入库且 market=global 无污染；抽样 20 条人工核对字段；频率统计空跑通（SQL 口径确定）；`docker compose up` 数据库就绪 |
| 自检重点 | Data：来源 100% 透明、中国市场与全球市场零混淆；Engineering：表只多不少（无"显得复杂"的表） |
| ⚠️ 本阶段风险 | 收集耗时（估 10 小时）+ Adzuna 免费额度节奏管理——止损线见 MVP.md §6 |

## Phase 3：JD Analyzer + Skill Extraction（含 E1 评测）

| 项 | 内容 |
|---|---|
| 目标 | 粘贴 JD → 结构化结果（含证据） |
| 产出 | LLM Gateway（Provider 抽象 + 单实现 + 缓存 + 重试）；抽取 Schema（Pydantic）；alias 归一化管道；证据可溯校验；**E1 标注集（50-100 条 JD）+ P/R/F1 计算 + 首轮基线报告**；Prompt 版本管理 |
| 验收 | E1 F1 ≥ 0.75（Warn 线起步，迭代冲 0.85）；证据可溯率 100%；失败用例（超长/乱码/无技能 JD）明示不静默 |
| 自检重点 | AI：LLM 是否被滥用（只抽取，无统计）；Evaluation：基线入库进回归历史 |
| 依赖 | Phase 2 数据集（标注集从中抽样） |
| 完成状态 | ✅ 代码与评测管道完成（2026-08-31，133 测试全绿；用户决策：DeepSeek + 种子集 20 条先行）；**真实基线待 LLM_API_KEY 配置后跑分**——详见根目录 PHASE_3_REVIEW.md |

## Phase 4：Market Intelligence

| 项 | 内容 |
|---|---|
| 目标 | 频率统计 + 溯源 + 样本量守门 |
| 产出 | 频率统计 SQL（整体/切片：岗位类/城市/薪资段）；market_snapshot 生成（含口径版本）；样本量 < 阈值返回"样本不足"；技能 → 支撑 JD 列表溯源端点；（预留）时间切片查询 |
| 验收 | 每个百分比可追溯到 JD 列表；统计口径文档化；与 MARKET_RESEARCH.md §2.1 小样本统计交叉对照（方向一致性检查，差异写入报告） |
| 自检重点 | Data：数字全部来自自有数据集；AI：统计代码零 LLM 依赖（CI 静态检查） |

## Phase 5：Candidate Profile

| 项 | 内容 |
|---|---|
| 目标 | 简历/手动输入 → 证据化画像 |
| 产出 | 简历文本/PDF 解析输入；证据识别（project_detail/project_desc/bare_claim 分类）；confidence 纯函数 + 权重规则表（公开）；手动勾选技能（manual 证据） |
| 验收 | 每技能输出证据片段 + confidence；权重公式单测全覆盖（含"熟悉 RAG"→低分边界用例）；3 个差异化画像测试用例固定 |
| 自检重点 | AI：confidence 为规则计算非 LLM；Product：证据呈现是否可被"死亡追问"式检验 |

## Phase 6：Skill Gap

| 项 | 内容 |
|---|---|
| 目标 | 岗位要求 vs 画像的差距量化 |
| 产出 | Gap 计算（重要度星级 vs 能力星级，含 confidence 折减）；transferable/genuine 区分（借鉴 JobBot 设计）；最大缺口清单（带 ROI 排序接口，供 Phase 7/8 使用） |
| 验收 | 单调用例：能力提升 → 缺口单调收窄；边界用例（完全无关岗位、完全达标岗位） |
| 自检重点 | Engineering：Gap 计算为纯函数；Resume：此阶段形成"可解释 Gap 报告"能力 |

## Phase 7：Job Matching

| 项 | 内容 |
|---|---|
| 目标 | 可解释匹配（基线 = Huntr 四维 + 我们的证据链加成） |
| 产出 | 确定性加权评分器（scoring_version 版本化）；分项 breakdown + Strong/Weak/Missing；LLM 解释生成（只文本）；**E2 标注集（20-30 对）+ Spearman/MAE/Jaccard 基线** |
| 验收 | E2 ρ ≥ 0.5 起步；单调性测试 100%；解释中每个数字与 breakdown 一致（程序比对）；可解释性对照 Huntr 基线自查（四维+覆盖状态+原因） |
| 自检重点 | AI：LLM 未影响任何分数；Evaluation：评分器版本与结果绑定 |

## Phase 8：Recommendation（引入 LangGraph，ADR-006 复议点）

| 项 | 内容 |
|---|---|
| 目标 | ROI 优先级建议 + （可选）Career Planner Agent |
| 产出 | ROI 公式实现（Demand×Gap÷Cost，纯函数+单测）；项目推荐模板库（人工策划，标注来源）；**Career Planner Agent（LangGraph 单 Agent）**：输入=确定性快照（只读），输出=建议解释，带 Trace/回放；**E3 评测**：nDCG@5 + 数值正确性 + 引用真实性 + LLM-as-judge（rubric 版本化）；（按需）RAG 引用层：pgvector 索引 + 检索引用"哪些 JD 要求 MCP" |
| 验收 | E3 nDCG@5 ≥ 0.5 起步；解释引用与 snapshot 一致率 100%；Agent 回放测试（同输入同 trace 确定性部分一致） |
| 自检重点 | AI：Agent 未篡改数值；Engineering：Agent 是否必要（若规则已达标记录复议结论） |

## Phase 9：Evaluation 汇总（系统级）

| 项 | 内容 |
|---|---|
| 目标 | 三层评测体系化 + CI 门禁 |
| 产出 | 评测集 v1 冻结（E1+E2+E3）；评测报告生成（指标表+版本三元组+与上版差异）；CI 集成（PR 快检 / main 全量 / 阈值 Block）；失败分诊流程文档化；EVALUATION.md（README 级文档） |
| 验收 | 同版本重跑确定性指标零漂移；LLM 指标方差 ≤ 3%；一次人为劣化演练（改坏评分权重 → CI 应拦截） |
| 自检重点 | Evaluation：结果可验证；Resume：形成"评测资产"（中文技能抽取标注集可开源） |

## Phase 10：Dashboard

| 项 | 内容 |
|---|---|
| 目标 | 数据与决策的可视化呈现（非聊天框） |
| 产出 | 六视图：画像（星级+置信度）/ Match Score / 技能雷达 / 热门技能（频率+样本量标注）/ 缺口（ROI 排序）/ 推荐学习与项目；每个数字可点击溯源（evidence_ref → JD/证据页） |
| 验收 | 六视图数据全部来自 API（无前端硬编码数字）；样本量守门在 UI 呈现；端到端用户流程走通（PRODUCT_SPEC §3） |
| 自检重点 | Product：展示数据和决策；Engineering：无花哨前端框架依赖 |

## Phase 11：Docker + CI + Documentation（发布就绪）

| 项 | 内容 |
|---|---|
| 目标 | clone → docker compose → import → run + 完整文档 |
| 产出 | Docker Compose 全栈编排；README（Problem/Solution/Architecture/Demo/Evaluation/Limitations/Roadmap，非营销文案）；ARCHITECTURE/DESIGN_DECISIONS/EVALUATION/DATA/API/DEVELOPMENT 文档终版；`docs/adr/` 归档（≥5 个 ADR 全部"已接受/已复议"）；一次完整自演示录制 |
| 验收 | 全新环境 clone 后按 README 三条命令内跑通；CI 全绿；文档与实现零偏差抽查 |
| 自检重点 | Resume：面试三问可答——数据从哪来（DATA.md）/为什么这么设计（ADR）/怎么证明有效（EVALUATION.md） |

---

## 里程碑与"简历价值"映射

| 里程碑 | 完成时你能在面试中说 |
|---|---|
| Phase 2 | "我人工构建并维护了一个带完整来源链的中文 JD 数据集，统计口径可复现" |
| Phase 3 | "我的技能抽取有 50-100 条人工标注集，F1 是 xx，每次 Prompt 变更有回归历史" |
| Phase 4-6 | "所有频率/置信度/缺口数字都是 SQL 和纯函数算的，LLM 只写解释——这是三层分离设计" |
| Phase 7 | "匹配分可以逐项拆解并追溯到 JD 原文，我对照过 Huntr 的可解释基线" |
| Phase 8 | "我先证明规则够用，才在需要推理的环节引入 LangGraph Agent，Agent 拿不到改数字的权限" |
| Phase 9 | "我建立了三层评测并让 CI 拦截过一次人为劣化——评测不是装饰" |
| Phase 11 | "clone 下来三条命令能跑，每个数字能溯源" |

---

## 全局纪律（贯穿所有阶段）

1. 每阶段结束执行六维自检（Product/Engineering/AI/Data/Evaluation/Resume），结果追加到本文档末尾的 Review 记录
2. 任何范围变更：先改 MVP.md/ADR，再动代码
3. 任何新增依赖：先补 ADR
4. 禁止跳过测试直接进入下一阶段；禁止一次生成多阶段代码

---

## Phase 0 自我 Review 记录（2026-08-31）

> 注：本节 ADR 编号为 Phase 0 旧编号，与 docs/adr/ 新编号映射见 DESIGN_DECISIONS.md §1（旧 ADR-001→新 003/004；旧 ADR-002→新 005；旧 ADR-004→新 001/002；旧 ADR-005→新 006）。

### Product —— 这个阶段真的解决问题吗？

是。Phase 0 回答了四个事前无法确定的问题：① 方向是否同质化（答案：简历匹配红海，但技能决策闭环空白）；② 数据是否可得（答案：公开频率数据不存在，须自建——风险已转为 MVP 止损线）；③ 差异化是否成立（答案：≥3 个空白功能，全部有证据）；④ 原方案是否需要修正（答案：核心叙事从"求职匹配"上移到"技能决策"，GitHub 分析降级 v2）。未做的：真实用户访谈（单人项目阶段以牛客面经作为需求侧代理信号，局限性已知）。

### Engineering —— 是否过度设计？

Phase 0 未写代码（符合要求）。设计层面已做三次"减法"：否决五 Agent 流水线（ADR-005）、pgvector 延后建索引（ADR-001）、Redis 收窄为缓存单一职责。模块数压在 6 个上下文内。风险：10 份文档本身有维护成本——已在全局纪律中规定"先改文档再动代码"来对冲文档腐化。

### AI —— LLM 是否被滥用？

产品设计中 LLM 被限制在抽取（Structured Output）与解释两个出口，统计/评分/ROI 数值全部确定性计算，且设 CI 静态检查（适应度函数）。研究过程本身由 LLM 辅助完成，但所有事实标注了核实状态，未核实数据未被用于决策依据。

### Data —— 数据是否真实？

三层纪律：① 每条事实标注 [已核实]/[线索]；② 培训机构口径数据明确排除；③ 产品输出的频率/薪资只允许来自自建数据集并附口径。发现的最重要的真实约束：中文 JD 无合法自动化数据源——已作为 ADR-004 冻结（手动粘贴优先），项目不建立在反爬对抗上。

### Evaluation —— 结果是否可验证？

评估方案先于代码存在（EVALUATION_PLAN.md）：三类评测、预声明阈值、版本三元组、失败分诊。诚实边界已写入：评测集规模只支撑相对回归比较，不支撑绝对能力宣称。

### Resume —— 是否产生值得写进简历的能力？

是：① 带完整来源链的中文 JD 数据集与统计口径（Phase 2 产出）；② 三层评测资产（中文技能抽取标注集，研究证明无现成基准，可开源）；③ 可 defending 的架构决策链（5 个 ADR 全部有 Forces/Alternatives/Reversibility）；④ "先研究后设计"的方法论本身（本目录 10 份文档即证据）。

### Phase 0 结论

**SkillGap Agent 值得做，且必须按修正后的定位做**：证据化技能决策系统（而非简历匹配工具）。差异化根基 = 自建数据集 + 证据化画像 + ROI 优先级 + 三层评测，四个支柱在竞品与开源研究双重排查下均为空白。
**遗留决策（阻塞 Phase 1）**：Q1 命名冲突（GitHub 已有 3 个同名项目）、Q2 数据集规模、Q3/Q4 范围确认——见 PRODUCT_SPEC.md §7。

---

## Phase 1 自我 Review 记录（2026-08-31）

### Product —— 这个阶段真的解决问题吗？

是。Phase 1 把 Phase 0 的研究结论转化为可执行的产品定义：MVP 以 MoSCoW 冻结（Must 11 项对应完整闭环）；用户贡献 JD 从导入附属升级为核心产品机制（F12，中国市场数据主通道）；市场统计按 China/Global 分离，回应"海外数据不能冒充中国统计"的真实约束。20 问自检见 PHASE_1_REVIEW.md。

### Engineering —— 是否过度设计？

否决项：五 Agent 流水线（延续 Phase 0）、v1 引入 LangGraph、pgvector 提前建索引、LLM 参与统计/评分。新增项全部有需求文档直接依据：Ingestion Context（三通道架构）、E5 数据质量评测、PII 管道（用户贡献机制的合规前提）。端点 16 个，全部对应 MVP M1-M11；ADR 9 个（需求要求 ≥8）。管道 S1-S12 每步有失败处理，无"以后再说"的半成品设计。

### AI —— LLM 是否被滥用？

LLM 仅两处受控节点：S8 技能抽取（Schema 校验 + 失败明示）、S12 解释生成（只读快照、禁输出数值）。统计/评分/ROI/PII/去重/质检全部确定性代码，CI 静态检查守门。Provider 抽象单实现（Q4 决议）。

### Data —— 数据是否真实？

三通道全部合法且可追溯：Adzuna（条款核查 2026-08-31，attribution 与额度纳入设计）、公司页面人工摘录（source_url）、用户 opt-in 贡献（PII 脱敏 + 匿名 + 可删除）。市场分离 DB 双保险；样本量守门 N<30 不出统计；USAJOBS 因条款禁止聚合被排除——宁缺数据不做违规集成。

### Evaluation —— 结果是否可验证？

评测体系扩为 E1-E5：新增 E5 数据质量（五指标 + 阈值 + 批次报告），与管道门禁 G1-G6 联动；Match Score 公式四项权重全部标记 configurable heuristic 待 E2 校准；评测集引用方式落定为冻结快照副本（复现性优先）。

### Resume —— 是否产生值得写进简历的能力？

是：① 合规数据架构（三通道 + Trust Tier + 市场分离 + API 条款核查记录）——展示数据工程判断力；② 数据质量评测（E5）——超出普通 AI 应用项目的能力面；③ 9 个可辩护 ADR；④ 诚实降级设计（样本量守门/PII 不声称 100%）——工程成熟度信号。

### Phase 1 结论

**设计冻结完成，未写任何业务代码（符合要求）。** 需求文档第三十七节要求的 11 项文档/目录全部齐备，另有 PHASE_1_REVIEW.md（根目录）。**已按第三十九节纪律停止，等待用户确认后进入 Phase 2。**

---

## Phase 2 自我 Review 记录（2026-08-31）

详见根目录 PHASE_2_REVIEW.md（六维全文 + 验收六项核验表）。

- **状态**：PASS WITH RISKS——代码与管道全绿（81 项测试全过），风险为两项用户执行项：首批 200-300 条人工收集、Adzuna 真实拉取（额度节奏）。
- **Product**：一条命令完成导入/拉取/贡献；批次报告（新增/重复/隔离/失败）入 ingest_batch 回归历史；200-300 条收集可以开跑。
- **Engineering**：21 张表全部来自 DATA_MODEL §2 + 管道支撑表，无自加业务表；SQL-first（ADR-010）；计划自检发现的死代码已清理。
- **AI**：零 LLM 依赖；S8 以 SkillExtractor 协议预留，LLM 实现属 Phase 3。
- **Data**：九字段 DB 强制（B1 以 IS NOT DISTINCT FROM 修复三值逻辑漏洞）；content_hash 双层去重；市场分离双保险；统计口径 SQL 常量冻结。
- **Evaluation**：E5 三项自动指标 + 阈值表 + 全库扫描 + PII 命中聚合；市场零混淆/幂等重跑/fail-closed/防探测删除等验收红线用例全绿。
- **Resume**："带 PII 三层防线与 fail-closed 语义的合规数据管道，统计口径冻结可复现，批次级数据质量指标入回归历史。"

---

## Phase 3 自我 Review 记录（2026-08-31）

详见根目录 PHASE_3_REVIEW.md（六维全文 + 验收核验表）。

- **状态**：PASS WITH RISKS——代码与评测管道全绿（133 项测试全过），风险为用户执行项：LLM_API_KEY 配置后真实基线跑分。
- **Product**：jd-analyze 一条命令输出 API §2.1 契约结构（含证据与 extraction_meta）；Phase 2 遗留 pending 抽取可回填。
- **Engineering**：migration 003 两表均为计划冻结项；模块依赖单向（analyzer → extractor → gateway → provider，eval 只读）；零新依赖（httpx 复用不加 SDK）。
- **AI**：LLM 仅 S8 抽取一个出口（Structured Output，temperature=0）；确定性字段由规则计算；E1 指标全部程序计算（红线：LLM 不参与指标）。
- **Data**：每条抽取技能带原文可定位证据；词表外进候选表不静默；缓存键含模型与 prompt 上下文防串味。
- **Evaluation**：E1 口径与阈值冻结（f1+recall 双闸、证据可溯率一票 block）；eval_run 回归历史；失败样本计漏不中断。
- **Resume**："LLM Gateway 防腐层（缓存+重试）+ 证据可溯校验的 Structured Output 抽取 + 20 条人工标注集与冻结阈值的回归评测器。"

