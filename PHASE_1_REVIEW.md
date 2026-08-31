# PHASE_1_REVIEW —— Phase 1 完成自检（20 问）+ 双角色评审报告

> SkillGap Agent ｜ 2026-08-31 ｜ 依据 Phase 1 需求文档第三十八节
> 状态：**PASS WITH RISKS（2026-08-31 双角色评审修复后终判，见文末评审章节）**
> 停机纪律：本文档即为停机报告——等待用户确认后才进入 Phase 2（不写代码、不建库、不装依赖）。

---

## 1. 最终产品是什么？

**SkillGap Agent：一个证据化技能决策系统**（不是简历匹配工具）。用户粘贴简历与目标 JD，系统输出：结构化 JD 分析、证据化技能画像（每技能带置信度）、可解释匹配分（四项确定性拆解）、分市场（中国/全球）技能频率统计（带样本量与来源分布）、技能缺口与 ROI 优先级建议。每个数字可溯源到 JD 原文、简历证据或统计快照；样本不足时明示。

## 2. 解决什么真实问题？

AI 方向求职者的三个真实困境（Phase 0 牛客面经证实）：① **不知道市场要什么**——公开渠道不存在可复现的中文技能需求数据（唯一公开统计是 23 条 JD 的非官方样本）；② **无法证明自己会**——"死亡追问"面试文化要求区分"声称会"与"证明会"；③ **不知道先补什么**——时间有限（7/14/30 天预算），"学 MCP 还是学 vLLM"没有可依据的计算。

## 3. 为什么这个问题值得解决？

市场规模真实且增长（AI 应用开发岗已独立成类，牛客/猎聘/智联报告交叉验证）；痛点高频（面经把 RAG/Agent 追问列为最高频考点）；竞品研究证明空白：无任何产品/开源项目覆盖"技能抽取→市场频率→证据化画像→Gap→ROI→Evaluation"完整链路（Huntr 做单 JD 匹配、JobBot 做 ESCO 归一、无一方做证据化+可复现统计）。且该问题对求职者有直接行动价值（省下的学习时间 × 更高的命中率）。

## 4. MVP 是什么？

M1-M11（Must Have，MVP.md §2.1）：JD 分析器、技能抽取+归一、**用户贡献 JD 通道（opt-in 匿名+PII 脱敏）**、数据导入与 Adzuna 海外 Ingest、证据化画像、四项确定性匹配、Skill Gap（transferable/genuine）、分市场频率统计（样本量守门）、ROI 推荐、六视图 Dashboard、E1+E5 评测基础。闭环：粘贴→画像→匹配→频率→缺口→建议→证据。

## 5. 删除了哪些原始功能？

① 求职匹配主叙事（降级为闭环一环）；② GitHub 仓库分析（v2）；③ RAG 知识问答（Phase 8+）；④ 技能趋势 7/30/90 天（数据积累后，Should Have）；⑤ Career Planner Agent（Phase 8）；⑥ PDF 简历解析（Should Have，文本粘贴先行）；⑦ 项目推荐模板库（Should Have）；⑧ 五 Agent 流水线构想（彻底否决，ADR-006）；⑨ Remotive 等多海外源（Could Have）；⑩ MCP Server 形态（Could Have）。

## 6. 为什么删除？

①匹配叙事：红海同质化（Huntr 等已做透），差异化上移到技能决策；②GitHub 分析：工程量大且简历证据已可闭环；③RAG：v1 解释用直接查库引用实现，向量检索无实际场景（不做"上传 PDF→聊天"的假 RAG）；④趋势：初始数据无时间跨度，强行输出=伪造趋势（诚实优于功能）；⑤Agent：v1 全部决策点（归一/统计/Gap/评分/ROI）是确定性计算，LLM 只做抽取与解释，不存在需要多步推理/状态/循环决策的环节；⑥-⑨：YAGNI，各有触发条件后才回加（MVP.md §2.2/2.3）；⑩五 Agent：把可解释白盒变黑盒链，与三层分离直接冲突。

## 7. 数据从哪里来？

三通道 + Trust Model（ADR-002）：**Tier A** = Adzuna 公开 API（Global 专用，条款已核查：免费层 250 请求/天、强制 "Jobs by Adzuna" 归属、无中国数据）+ 公司官方招聘页人工摘录（记 source_url）；**Tier B** = 用户 opt-in 匿名贡献（中国市场主通道）；**Tier C** = CSV/JSON 社区导入 + 内置 Demo Dataset。每条数据强制九字段：source_type/source_name/source_url/collected_at/submitted_at/content_hash/license_or_usage_note/consent_status/data_quality。

## 8. 中国岗位数据怎么获得？

**用户主动粘贴 JD（主通道）**：用户在 BOSS/牛客等软件自行看到岗位后复制粘贴，分析后选择匿名贡献（PII 脱敏→去重→质检→入库）；**公司官方招聘页人工摘录**（如腾讯 hr.tencent.com，记录 URL 与时间）；**社区 CSV/JSON 批量贡献**；**人工收集 Demo Dataset**（200-300 条，约 10 小时，分批校准词表）。核心思想：不获取"全部数据"，而是获得**足够真实、可追溯、合法来源**的中国 JD。

## 9. 为什么不爬 BOSS？

三层理由（ADR-001）：① **合法性**——平台条款禁止自动化采集，绕过登录/验证码/反爬有法律与不正当竞争风险，单开发者无力承担；② **工程性**——项目会建立在反爬对抗的脆弱地基上，平台一改版数据管道即崩，产品永续性为零；③ **产品性**——爬来的大规模无来源数据反而违背"可追溯"的差异化根基。禁令是硬约束不是待绕过的问题；触红线 PR 一律拒绝合并。

## 10. 用户贡献数据怎么工作？

```
用户粘贴 JD → 即时 JD 分析（先交付个人价值）
→ 结果页 opt-in 询问"匿名贡献到市场数据集"（默认不勾）
→ PII 检测（正则：手机/邮箱/微信/QQ/联系人/身份证）
→ PII 脱敏（[PHONE_REDACTED] 等标记替换，保留可读性）
→ content_hash 去重 → 质量校验 → 技能抽取
→ 市场数据集（consent_status=market_analysis，source_type=user_submitted）
```

匿名（不记身份）；一次性 deletion_code 支持删除；重复提交返回已有记录不算错误。用户主动提交与平台自动抓取在数据模型与治理上严格区分。

## 11. 如何保护用户隐私？

① **PII 三层防线**：版本化正则规则（主体，可审计可回放）→ 人工抽查（固定比例抽样复核）→ quarantine 人工复核队列；② **不声称 100%**——文档与 UI 明示残余风险，发现漏检即升级规则版本并重扫存量；③ **简历数据**永不进入市场统计，仅本人可见，30 天不活动过期，可随时删除；④ **匿名贡献** + 删除机制（deletion_code 哈希存储，防探测）；⑤ **raw 暂存** 7 天后物理删除；⑥ 中国合规基线：贡献即脱敏、最小化收集、无账号无追踪。

## 12. 当前系统架构是什么？

**模块化单体 + 三层智能分离**：Dashboard → FastAPI → 应用核心（Ingestion / JD / Market / Candidate / Matching / Recommend 六个有界上下文 + LLM Gateway + Evidence Layer）→ PostgreSQL（pgvector 预留不建索引）+ Redis（缓存）。外部数据源经 Ingestion Context（防腐层）进入。v1 无 Agent（规则+排序），Phase 8 才引入 LangGraph 单 Agent。

## 13. 为什么这样设计？

① **单体优先**：单人项目，微服务化纯付复杂度税，无任何命名收益；② **三层分离（ADR-005）**：确定性层（统计/评分/ROI，SQL+纯函数）保证数字可复现可单测，LLM 层只做抽取与解释（禁改数值），Evidence 层让每个结论可回链——这直接回应"LLM 黑盒不可信"的市场疑虑，也是对 Huntr 可解释基线的升级；③ **防腐层**：外部源（Adzuna/用户输入/LLM 输出）都过 Ingestion/Gateway 翻译成内部 Schema，外部变更不传染核心；④ **市场分离**：海外/中国数据混算即造假，DB+服务层双保险。

## 14. 最大技术风险是什么？

**中文技能抽取质量**（E1 F1 能否达 0.85）。中文 JD 表述变体多、程度词（精通/熟悉/了解）需映射、词表外新词需归一——这是唯一无法用确定性代码兜底的环节。缓解：Structured Output+Schema 校验+alias 归一+E1 标注集回归（50-100 条）+止损线（F1<0.75 三轮无改善则缩小词表保高频 15 技能）。次风险：Match Score 权重是 heuristic（需 E2 标注集校准，已标记 configurable）。

## 15. 最大数据风险是什么？

**中国市场数据积累不及预期**（差异化根基失效）。合规通道天花板低：用户贡献依赖冷启动、人工摘录每条约 3 分钟、Adzuna 又无中国数据——中国统计可能长期停在"样本不足"。缓解：止损线（2 周 <100 条则缩小到"AI 应用开发"单一切片保深度）、贡献体验优化（分析后一键贡献）、Demo Dataset 人工兜底。次风险：Adzuna 条款/额度变动（缓解：代码与数据分离，周级快照降频）。

## 16. 最大产品风险是什么？

**同质化误判 + 价值感知不足**：① 若竞品（Huntr 等）扩展出证据化画像，差异化窗口收窄——缓解：README 差异声明+持续竞品复查；② 用户可能只把它当"又一个匹配工具"用（粘贴 JD 看匹配就走，不贡献数据）——数据飞轮转不起来，统计永远是空壳。缓解：个人价值先行（分析即时有用），贡献是分析后的自然延伸而非前置条件；③ 真实用户访谈缺失（Phase 0 已知局限，以牛客面经为需求侧代理）。

## 17. 最难实现的部分是什么？

**① 中文技能抽取 + Taxonomy 归一的联合质量**：抽取准确（E1）与归一正确（LangChain.js→LangChain）必须同时成立，且新词候选需要持续人工裁决；**② E1 标注集本身**：50-100 条中文 JD 的人工标注（含 κ 一致性抽检）是无人替代的苦活，却是评测体系的地基；**③ 证据置信度权重表设计**：project_detail 1.0 / project_desc 0.6 / bare_claim 0.3 的取值需要用例打磨才能区分"0.45 vs 0.91"的质感。

## 18. 哪些地方最值得写进简历？

① **合规数据架构**：三通道+Trust Tier+市场分离+API 条款核查记录（Adzuna 采用/USAJOBS 排除的判断过程）——展示数据工程与合规判断，区别于"接个 API"水平；② **三层分离设计**：确定性层/LLM 层/证据层+CI 静态检查"统计模块零 LLM 依赖"——可辩护的架构观；③ **E1+E5 评测体系**：中文技能抽取标注集（无现成基准，本身可开源）+数据质量五指标门禁——证明"评测先于代码"；④ **9 个 ADR**：完整决策推理链（含被否方案），面试"为什么"问题的弹药库；⑤ **诚实降级**：样本量守门/PII 不声称 100%/市场分离——工程成熟度信号。

## 19. 哪些功能虽然听起来高级但应该暂时不做？

① **Multi-Agent 流水线**（五 Agent 各管一段）——最诱人也最有害：把白盒计算包成黑盒链，纯为简历关键词；② **RAG 知识库**——v1 用直接查库即可实现带引用解释，提前上 pgvector 是"为展示而 RAG"；③ **实时趋势看板**（7 天技能变化）——数据没积累够，输出即伪造；④ **LLM 打分**——一行代码出分数最省事，但毁掉整个可信度设计；⑤ **GitHub 代码证据分析**——高级且差异化，但工程量大，简历证据已可闭环，v2 再做；⑥ **USAJOBS/多源并发接入**——看起来数据丰富，实则条款风险。

## 20. Phase 2 应该先做什么？

**按 ROADMAP Phase 2**：① PG Schema 落地（全部约束：来源九字段/content_hash 唯一/market 分离/status 过滤）；② **Ingestion 管道实现**（S1-S10：Adzuna 连接器+CSV/JSON 导入器+用户贡献通道+PII 规则库+质检 quarantine）；③ E5 数据质量指标（批次报告）；④ 人工收集首批 50 条中文 JD 试跑管道并校准词表（先小批验证再放量到 200-300）；⑤ 词表 v1 正式建档。**建议顺序：管道与 Schema 先行，数据收集与管道调试交错进行**——避免"先攒 300 条数据再发现管道要改"的返工。

---

## 附：Phase 1 交付物清单核验（需求第三十七节）

```
docs/
├── MVP.md ✅（MoSCoW + 数据质量门禁）
├── PRODUCT_SPEC.md ✅（Phase 1 冻结版）
├── ARCHITECTURE.md ✅（Phase 1 冻结版 + Ingestion Context）
├── DATA_MODEL.md ✅（Phase 1 冻结版 + 市场分离 + Match Score 公式）
├── DATA_PIPELINE.md ✅（S1-S12 分步规格）
├── DATA_GOVERNANCE.md ✅（合规/PII/保留/API 条款核查/反爬声明）
├── API.md ✅（16 端点 + 错误处理）
├── UI_SPEC.md ✅（7 页面）
├── EVALUATION_PLAN.md ✅（E1-E5，E2 含 P/R/F1 + Correlation + MAE + Jaccard + 单调性）
├── DECISION_LOG.md ✅（9 条决策记录，含本次评审 D-2026-08-31-09）
└── adr/ ✅（ADR-001~009，含需求指定的 8 个主题）
```

**已停止。等待确认。**

---
---

# Senior Engineer + Product Architect Review（2026-08-31）

> 评审对象：Phase 1 全部交付物（docs/ 10 份文档 + 9 个 ADR）+ 根目录 2 份提示词原始记录
> 评审基准：`Phase1_需求冻结与架构设计提示词.md`（39 节）逐节对照；Phase 0 三份研究文档作为衍生依据
> 评审方法：十项检查点 → 问题分级（BLOCKER/HIGH/MEDIUM/LOW）→ 修复 → 逐项复核 → 终判

## R1. 十项检查点结论

| # | 检查项 | 结论 | 依据 |
|---|---|---|---|
| 1 | 是否完整满足 Phase 1 要求 | **通过（修复后）** | 需求第三十七节文档清单 100% 齐备；第三十六节 8 个指定 ADR 主题全覆盖；第十五节 MoSCoW / 第二十五节评测指标（修复 H8 后）/ 第二十九节 Provider 接口（修复 H5 后）/ 第三十四节管道分步（输入/输出/失败/LLM/人工五要素）均达标 |
| 2 | 需求遗漏 | **无遗漏（修复 3 处后）** | B2（第十七节 Parent/Related Skill）、B3（第二十节 Experience Relevance 的输入字段）、H8（第二十五节 Matching P/R/F1）曾缺失，均已补齐 |
| 3 | MVP 范围膨胀 | **无膨胀** | Must Have = M1-M11，与第十六节核心闭环一致；Adzuna 进 M4 是需求第十节明确要求（非自加）；删减清单（Q5）10 项均保留在 Should/Could/Won't；无任何未经用户决议的新增 Must |
| 4 | 架构设计问题 | **无结构性问题** | 模块化单体 + 三层分离与需求第十四节一致；B2 修复后 Taxonomy 数据基础补全；H4 修复后 LLM 受控节点表述准确；无过度设计（pgvector 只预留表不建索引、Redis 仅缓存、v1 无 Agent） |
| 5 | 数据模型/API/模块一致性 | **一致（修复 5 处后）** | 复核链：skill_relation（DATA_MODEL §2.4）↔ §4.4 transferable 判定 ↔ API §2.9 gaps 端点；soft_requirements（§2.2）↔ API §2.1 ↔ Match 公式；soft_profile（§2.7）↔ API §2.5 ↔ §4.3 中性值；S8/S12 ↔ Provider 两方法；模块-端点映射齐全（M2 在管道内、M10 为 UI 层，其余模块各有端点承载） |
| 6 | 硬约束合规 | **全部合规** | 无任何爬虫/绕过登录/验证码/反爬路径（API 全表、管道 S1-S12、ADR-001 交叉核验）；数据源均有依据：Adzuna 条款核查（attribution + 限额 + 数据不分发）、USAJOBS 排除、用户贡献 opt-in + PII 管道；"用户主动提交 ≠ 平台抓取"在 DATA_MODEL（consent 字段）与 DATA_GOVERNANCE（治理）双落地 |
| 7 | LLM/Agent/传统代码职责划分 | **合理** | LLM 仅 S8 抽取 + S12 解释（禁数值）；统计/评分/ROI 全确定性（CI 静态检查 + 适应度函数 §9）；Agent 延后 Phase 8 有 ADR-006 推理链（五段图=数据流水线非五个 Agent） |
| 8 | 数据流完整且可追踪 | **完整** | 输入 → S1-S10 入库 → S11 统计 → 匹配/缺口/ROI → UI，每环带 evidence_ref；九字段 + content_hash + consent 过滤（B1 修复后统计口径三文档一致：DATA_MODEL §3 / API §2.1 / DATA_PIPELINE S11）；失败路径全部显式（quarantine/extraction_failed/样本不足） |
| 9 | Evaluation 能否验证核心价值 | **能** | 核心价值=证据化技能决策：E1 守抽取质量（F1 门槛）、E2 守匹配公式（P/R/F1 + ρ + 单调性）、E3 守 ROI 排序（nDCG + 公式重算 100%）、E5 守数据根基（五指标门禁）；E2/E3 直接检验"分数与建议可信"，E5 直接检验"数据真实"——三根差异化支柱各有评测锚点 |
| 10 | 不修即返工的问题 | **已消除** | 原 BLOCKER×3 全部属此类（同意漏洞会导致贡献数据全部污染统计、Taxonomy 缺失导致 M7 无法实现、Match 公式缺输入导致 Phase 7 重写），均已修复；剩余 MEDIUM 均有明确关闭阶段 |

## R2. 问题清单与处置

### BLOCKER（3 项，已全部修复）

| # | 问题 | 危害 | 修复 |
|---|---|---|---|
| B1 | 统计口径同意漏洞：`DATA_MODEL §3` 统计过滤仅 `status='active'`，未排除 `consent_status=none` 的用户提交记录；`/api/jd/analyze` 带 `save` 参数可未经同意入库 | 违反 opt-in 承诺（合规红线）；未授权数据混入统计毁掉"数据可追溯"根基 | 统计条件改为 `status='active' AND (source_type != 'user_submitted' OR consent_status='market_analysis')`；移除 `save` 参数，分析无状态不落库，入库唯一通道 `/api/jd/contribute`（consent=true）；DATA_PIPELINE S11 输入同步该口径 |
| B2 | Taxonomy 缺 Parent/Related 建模：需求第十七节要求，但 `skill` 表无层级字段、无关联表 | M7 transferable 判定无数据基础（只能硬编码）；Phase 6 返工 | `skill` 增 `parent_skill_id` 自引用；新增 `skill_relation` 表（`related` / `transferable_to`，对称双行 + note）；§4.4 冻结 genuine/transferable 判定规则 |
| B3 | Match 公式输入缺失：`experience_relevance` 权重 0.10，但 job 无软性要求存储、candidate 无经验/学历字段 | 公式无法实现（Phase 7 才发现=大面积返工） | `job.soft_requirements` jsonb（type/value/evidence_text）+ `candidate.soft_profile` jsonb（experience_years/education/languages，附证据）；API 两端点响应字段同步 |

### HIGH（8 项，已全部修复）

| # | 问题 | 修复 |
|---|---|---|
| H1 | Gap 星级口径不一致：程度词→等级映射缺失，gap 与 confidence 混淆 | §4.2 映射表（精通=5/熟练=4/熟悉=3/了解=2，nice_to_have 封顶 2）；§4.4 明确 gap=星级差，confidence 不进 gap（仅进 conf_factor） |
| H2 | ROI 除法不可计算：learning_cost 为 Low/Mid/High 枚举 | §4.2 枚举→数值映射（Low=1/Mid=2/High=3），展示层仍用枚举 |
| H3 | ARCHITECTURE 陈旧引用（"规划文档第 N 节"指向错位） | 引用改为"需求第 N 节"并逐条核对章节号；复核确认剩余"规划文档"字样均指向根目录原始规划文档且章节真实存在（§20 Evaluation、§35 六维自检、五段图） |
| H4 | "M1-M8 全部是确定性流程"事实错误（M1/M2/M5 含 LLM 抽取） | ARCHITECTURE §6 方案 A 判决改为"决策链路全部确定性，LLM 仅存在于抽取与解释受控节点"；本文档 Q6 同步修正 |
| H5 | Provider 接口与需求第二十九节不符 | 重构为 `generate` / `generate_structured(prompt, schema)` / `embed`（v1 抛 NotImplementedError），业务层零厂商 SDK 依赖 |
| H6 | API 未声明"无鉴权仅限本地"前提 | API §0 新增部署边界红线：MVP 仅限本地单用户部署，公网部署前必须先加认证与速率限制 |
| H7 | PRODUCT_SPEC F5 写"MVP：方式 A/B/C"（含 PDF）与 MoSCoW（PDF=Should Have）矛盾 | F5 改为"MVP：方式 B/C；Should Have：方式 A PDF"；核心流程图同步（文本为主通道，PDF 标注 Should Have） |
| H8 | E2 缺需求第二十五节指定的 Matching P/R/F1 | §3.2 新增技能三组分类 P/R/F1（micro 主报 Missing 组，macro 辅助；F1 ≥0.7 Pass），与 Correlation（Spearman ρ）、MAE、Jaccard、单调性并存 |

### MEDIUM（3 项，记录在案，按阶段关闭）

| # | 问题 | 关闭时点 |
|---|---|---|
| M1 | 英文程度词映射缺失：`intensity` 枚举仅中文程度词，Global 市场（Adzuna 英文 JD）的 expert/proficient/familiar 等映射表未定义 | Phase 3 冻结抽取 Schema 词表时一并定义（S8 英文侧） |
| M2 | 简历 → `candidate_skill.level`（1-5 星）的推导规则未定义（evidence 只决定 confidence，level 缺独立规则） | Phase 5 实现前冻结映射规则并纳入 E2 边界用例 |
| M3 | `skill_relation` / `parent_skill_id` 的种子数据未列入词表 v1 建档范围（ROADMAP Phase 2 只写 skill/alias 初版）——无种子数据则 M7 transferable 判定空转 | Phase 2 词表建档时同步补 parent/relation 初版（至少覆盖 Java→Python 等已声明的迁移对） |

### LOW（3 项，暂不处理）

| # | 问题 | 理由 |
|---|---|---|
| L1 | API 端点总表未单列 `GET /api/tasks/{task_id}`（正文 §0 与 §2.2 已引用，语义完整） | 文档排版细节，Phase 2 契约测试时顺手补 |
| L2 | DATA_GOVERNANCE §5 "无 confirm 即删 + 二次确认 UI" 措辞自相矛盾（实际语义：删除即时生效，UI 提供二次确认） | 表述瑕疵，无实质歧义 |
| L3 | ROADMAP Phase 5 产出含"PDF 解析输入"，与 MoSCoW（PDF=Should Have）表述待对齐 | Should Have 允许 Phase 5 内后置实现，无冲突，执行时对齐即可 |

## R3. 修复复核（Re-review 结果）

| 修复项 | 复核点 | 结果 |
|---|---|---|
| B1 | DATA_MODEL §3 统计条件 / API §2.1 无 save 参数 + 入库唯一通道 / DATA_PIPELINE S11 输入口径 | ✅ 三处一致 |
| B2 | skill 表字段 / skill_relation 表 / §4.4 判定规则 / API §2.9 响应 | ✅ 闭环 |
| B3 | job.soft_requirements / candidate.soft_profile / API §2.1 与 §2.5 响应 / §4.3 中性值守卫 | ✅ 闭环 |
| H1+H2 | §4.2 枚举→数值映射三行表 + §4.4 gap 公式 | ✅ 可计算 |
| H3 | 全库"规划文档"引用逐条核对（ROADMAP/PRODUCT_SPEC/EVALUATION_PLAN/ARCHITECTURE/COMPETITOR/OPEN_SOURCE/ADR-001） | ✅ 剩余引用全部指向真实存在的原始文档章节 |
| H4 | ARCHITECTURE §6 方案 A / PHASE_1_REVIEW Q6 | ✅ 表述与 API.md LLM 列（M1/M3/M4/M5 抽取、M6/M9 解释可选、M7/M8 禁止）一致 |
| H5 | Provider 三方法 vs 需求第二十九节原文 | ✅ 字面一致 |
| H6 | API §0 部署边界 | ✅ 就位 |
| H7 | PRODUCT_SPEC F5 + §3 流程图 vs MVP.md §2.2 vs UI_SPEC §2.3（本就正确） | ✅ 三文档同口径 |
| H8 | E2 指标表 vs 需求第二十五节（P/R/F1 + Correlation） | ✅ 齐备 |

## R4. 硬约束合规核验（专项）

| 硬约束 | 核验结果 |
|---|---|
| 禁止招聘平台爬虫 | ✅ 端点全集 / 管道 S1-S12 / 技术栈表均无爬虫路径；ADR-001 完整推理；DATA_GOVERNANCE §8 红线清单 + CI 层无爬虫依赖检查计划；触线 PR 拒绝合并 |
| 禁止绕过登录/验证码/反爬 | ✅ 无任何涉及；S1 明确"代码不含数据、用户自行运行 ingest"的合规隔离 |
| 数据来源合法依据 | ✅ 每源有据：Adzuna（条款核查记录 + attribution 义务 + 限额遵守 + 数据不分发）、公司招聘页（source_url 必填）、用户贡献（opt-in + PII 三层 + deletion_code）、USAJOBS 明确排除、Greenhouse/Lever 暂缓有理由 |

## R5. 最终判定

## **PASS WITH RISKS**

**判定理由**：
- **通过面**：Phase 1 交付物 100% 齐备（需求第三十七节）；3 项 BLOCKER 与 8 项 HIGH 全部修复并逐点复核；MVP 无范围膨胀；三项硬约束全部合规；数据模型-API-模块-评测四方一致；Evaluation 覆盖三根差异化支柱。
- **保留风险（已识别、有缓解、不阻塞 Phase 2）**：
  1. **MEDIUM×3 待按阶段关闭**（英文程度词 Phase 3 / level 映射 Phase 5 / skill_relation 种子数据 Phase 2）——均已写入 DECISION_LOG D-2026-08-31-09；
  2. **Match 与 confidence 权重均为 configurable heuristic**——需 Phase 7 E2 标注集校准后升 scoring_version（设计内风险）；
  3. **中国市场数据积累不及预期**——冷启动依赖用户贡献与人工摘录，止损线已定义（2 周 <100 条缩小切片）；
  4. **E1 中文抽取质量是最大技术不确定性**（F1 0.75 起步线）——评测先行的架构已把该风险隔离在可控迭代环内。

**结论：Phase 1 冻结有效。已停止，不进入 Phase 2，等待用户确认。**
