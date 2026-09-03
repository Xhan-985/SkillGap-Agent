# DECISION_LOG —— 决策日志

> SkillGap Agent ｜ Phase 1 交付物
> 记录产品与技术方向的**时序决策**（为什么改、何时改）。与 ADR 的分工：ADR 记录"决策的完整推理"，本日志记录"决策的变更轨迹"。

---

## D-2026-08-31-01 ｜ 项目定名 SkillGap Agent

- **背景**：暂定名 JobLens 与 GitHub 上 3 个同名项目冲突（OPEN_SOURCE_RESEARCH §1）
- **决策**：定名 **SkillGap Agent**，放弃暂定名
- **影响**：全部文档名称统一；原始规划文档保留于根目录（其中 JobLens 为暂定名）

## D-2026-08-31-02 ｜ MVP 定义重构为 MoSCoW 结构

- **背景**：Phase 1 需求（第十五节）要求 Must/Should/Could/Won't Have 结构重定义 MVP，且新增用户贡献 JD 与数据质量门禁要求
- **决策**：MVP.md 重写为 MoSCoW；M1-M11 为 Must Have；数据质量门禁 G1-G6 单列成章（§4）
- **变更**：Phase 0 版 M3"内置 Demo Dataset + 导入"升级为 M4"数据导入与海外 Ingest"（Adzuna 进 MVP）；新增 M3"用户贡献 JD 通道"
- **保持**：核心闭环（粘贴→画像→匹配→频率→缺口→建议）与 Phase 0 一致

## D-2026-08-31-03 ｜ 数据源从"远期候选"升级为"第一阶段架构"

- **背景**：Phase 0 ADR-004 将 Adzuna/ATS API 列为"远期候选"；Phase 1 需求（第十节）明确海外公开岗位作为第一阶段稳定、可自动化的数据来源，且必须核查条款
- **核查结论**（2026-08-31）：Adzuna 可用（Tier A，Global 专用，250 req/day，强制 attribution，无中国数据）；USAJOBS **排除**（条款禁止聚合衍生）；Remotive 备选（4 次/天限制）；Greenhouse/Lever 暂缓（无官方公开条款页）
- **决策**：Adzuna 进入 MVP（M4）；建立 Trust Model（Tier A/B/C）与**中国/全球市场分离**（DB 双保险 + 统计强制分组）；开源仓库只分发连接器代码、不分发 Adzuna 数据（合规隔离）
- **依据**：DATA_GOVERNANCE §6 ｜ ADR-002

## D-2026-08-31-04 ｜ 用户贡献 JD 成为产品机制（非单纯导入）

- **背景**：需求第五/六节将用户贡献 JD 定义为重要产品机制（opt-in 匿名贡献 + PII 管道），而非 Phase 0 设计的 CSV 导入附属
- **决策**：F12 功能（PRODUCT_SPEC）；贡献流程：分析完成 → opt-in → PII 检测/脱敏 → 去重 → 质检 → 入库；匿名 + 一次性 deletion_code 支持删除；**不声称 100% PII 识别**（三层防线）
- **影响**：数据模型新增 deletion_code 表；UI_SPEC 新增贡献区设计

## D-2026-08-31-05 ｜ 评测体系新增 E5 数据质量

- **背景**：需求第二十六节要求数据质量 Evaluation（Duplicate/Missing Field/PII/Invalid JD/Skill Extraction Error），使项目具备数据工程能力证明
- **决策**：EVALUATION_PLAN 新增 E5（五指标 + Pass/Warn/Block 阈值 + 批次报告与回归）；与管道门禁 G1-G6 联动
- **保持**：E1-E4 原设计不变

## D-2026-08-31-06 ｜ Match Score 公式冻结（四项加权）

- **背景**：需求第二十节要求 Match Score = Coverage + Importance + Evidence Confidence + Experience Relevance，权重必须有依据
- **决策**：`Overall = 100 × (0.45×coverage + 0.25×importance_coverage + 0.20×evidence_quality + 0.10×experience_relevance)`，权重依据见 DATA_MODEL §4；全部标记 **configurable heuristic**，Phase 7 E2 标注集校准后升 scoring_version
- **红线**：LLM 在匹配路径零数值参与

## D-2026-08-31-07 ｜ ADR 体系迁移与扩编

- **背景**：需求第三十六节要求 docs/adr/ 至少 8 个指定主题 ADR；ROADMAP Phase 1 计划将 DESIGN_DECISIONS.md 的 5 个 ADR 迁入
- **决策**：docs/adr/ 建档 ADR-001~009（8 个指定主题 + 保留 Phase 0 技能抽取决策为 ADR-009）；DESIGN_DECISIONS.md 转为索引 + 决策总表 + 风险登记表
- **映射**：旧 ADR-001→新 003/004；旧 ADR-002→新 005；旧 ADR-003→新 009；旧 ADR-004→新 001/002；旧 ADR-005→新 006

## D-2026-08-31-08 ｜ Phase 0 遗留四项决策落定

| 遗留项 | 落定 |
|---|---|
| job_category 词表 | 8 类枚举 + 海外源映射表（DATA_MODEL §5.1） |
| pgvector 表结构 | jd_embedding 预留，不建索引（ADR-004） |
| 评分器 versioning | scoring_version 语义化版本绑定评测结果 |
| 评测集引用方式 | 冻结快照副本（input_payload 入库，非外键）——评测复现性优先 |

## D-2026-08-31-09 ｜ Phase 1 评审（Senior Engineer + Product Architect Review）

- **背景**：用户要求对 Phase 1 全部交付物做双角色评审（10 项检查点：完整性/遗漏/范围膨胀/架构/一致性/硬约束/职责划分/数据流/评测有效性/返工风险），问题分级后修复 BLOCKER 与影响架构的 HIGH
- **发现**：**BLOCKER×3**（B1 统计口径同意漏洞 / B2 Taxonomy Parent-Related 建模缺失 / B3 Match 公式输入缺失）＋ **HIGH×8**（H1 Gap 星级口径 / H2 ROI 枚举除法 / H3 陈旧引用 / H4 "M1-M8 全确定性"事实错误 / H5 Provider 接口不符 / H6 API 部署边界未声明 / H7 F5 与 MoSCoW 矛盾 / H8 E2 缺 P/R/F1）＋ MEDIUM×3 ＋ LOW×3
- **决策**：当日修复全部 BLOCKER 与 HIGH（涉及 DATA_MODEL / API / ARCHITECTURE / PRODUCT_SPEC / EVALUATION_PLAN / DATA_PIPELINE 六份文档）；MEDIUM 按阶段关闭：英文程度词映射→Phase 3 词表冻结时、candidate level 映射规则→Phase 5 前、skill_relation 种子数据→Phase 2 词表建档时
- **终判**：**PASS WITH RISKS**（详见 PHASE_1_REVIEW.md 评审章节）——交付物 100% 齐备、硬约束全部合规、无范围膨胀；保留 heuristic 待 E2 校准与中国数据积累两项已识别风险

## D-2026-08-31-10 ｜ 持久层选型：psycopg3 + SQL 迁移文件（无 ORM）

- **决策**：持久层采用 psycopg3 + 版本化 SQL 迁移文件（无 ORM）；新增依赖 httpx / pydantic-settings（均为最小依赖）
- **关联**：ADR-010
- **影响**：Phase 2 启动——迁移以 .sql 文件为单一事实源，统计/约束/口径全部 SQL 可审计；后续 FastAPI 层同样走 psycopg + Pydantic

## D-2026-09-03-11 ｜ confidence 公式冻结（conf-v1）

- **决策**：`confidence = min(1.0, Σᵢ w₍ᵢ₎ × 0.5^(i-1))`（证据权重降序 + 次数衰减 γ=0.5）；权重 project_detail=1.0 / project_desc=0.6 / bare_claim=0.3 / manual=1.0，与 candidate_evidence.weight 的 DB CHECK 严格一致
- **关联**：DATA_MODEL §2.7、docs/WEIGHT_RULES.md（公开交付物，含逐例演算）
- **影响**：Phase 5 落地；level 与 confidence 正交（gap 用星级、match 用 conf_factor——H1 修复的口径延续）

## D-2026-09-03-12 ｜ 简历重分析替换式 + manual 行保留

- **决策**：同一 candidate 重新分析 → 删除其全部 source_type='resume_text' 技能行后插入新结果（简历=当前状态快照，陈旧证据不跨版本累积）；manual 行永不删除，与新简历冲突时跳过插入 + 显式 notice（manual_overridden）；add_manual_skill 整行替换已有行（用户显式意图最新）；手动勾选仅接受词表内技能（new_skill_candidate 保持 LLM 新词裁决通道纯净）
- **影响**：Phase 5 服务层语义（D1/D5），测试锚定 test_profile_service.py

## D-2026-09-03-13 ｜ gap-v1 冻结：confidence 不进 gap + 类目聚合规则

- **C1 口径裁决**：ROADMAP Phase 6 产出原文"含 confidence 折减"与 DATA_MODEL §4.4（H1 修复）"confidence 不直接进 gap"冲突——按 DATA_MODEL 裁决：**gap = 纯星级差** `clamp(required−actual, ≥0)`；conf_factor 属 Phase 7 match 公式。ROADMAP 措辞已同步修正
- **C2 类目聚合规则冻结**（API §2.9 原文只留一句"市场聚合要求"）：类目内出现频次 ≥ min_freq（默认 0.20）的技能进入要求清单；required_level = 该技能类目内 must_have 行映射最大值（无 must_have 行取 2）；demand = frequency + sample_size + 最新快照引用
- **D1 映射缺省**：intensity NULL → must_have 取 3（熟悉中性档）/ nice_to_have 取 2；nice_to_have 一律封顶 2
- **D3 transferable 判定**：相关技能集 = {s} ∪ parent（一层）∪ transferable_to 双向；集合内存在 confidence ≥ 0.5 证据 → transferable（via 报证据技能，note 取 relation.note），否则 genuine
- **排序**：gap 降序、同 gap 按 frequency 降序；ROI 公式（Demand×Gap÷Cost）属 Phase 8 roi-v1，本阶段只输出 demand/cost 原料不计算分值
- **影响**：Phase 6 落地（src/skillgap/gap/，版本 gap-v1，零 LLM/零迁移/零新依赖）；min_freq 与 evidence 线 0.5 为 heuristic 首值，E2/Phase 7 校准后升版本

## D-2026-09-03-14 ｜ match scoring 1.0.0 冻结：满足性口径 + 三组规则 + C1/C2 裁决

- **C1 口径裁决（experience_relevance 数据现状）**：DATA_MODEL §4.1 要求 JD 侧 soft_requirements 参与经验相关性，但探测发现真实库 201 条 JD 的 soft_requirements **全部为空**（jd-analyze 管线从未抽取存储）——v1.0.0 实现完整软性匹配逻辑（年限≥/学历包含/语言包含→逐项匹配率），但真实数据下恒走 §4.3 中性 0.5 分支（neutral_flags: soft_not_evaluable 明示）。回填需 E1 prompt 变更（走 E1 评测门禁），Phase 7 不做
- **C2 口径裁决（E2 校准纪律）**：基线一次 pass（ρ=0.84）未触发校准；若未来触发：每轮升 scoring_version patch 号 + eval_run 留痕 + 变化 <3% 视为噪声不调参；同集校准的过拟合风险如实记录（25 对小样本，v2 扩集后复验）
- **D2 满足性**：计入 coverage 的 ach_w ⇔ actual_level ≥ required_level（required_level 复用 gap-v1 映射，单一事实来源）；conf_factor = 0.5+0.5×confidence **只折减贡献权重不改变满足性**——与 gap 的 confidence 不进 gap 互补，共同构成 H1 修复两面
- **D4 三组规则**：missing ⇔ 画像无记录；strong ⇔ 满足 ∧ confidence ≥ 0.5（与 gap-v1 证据线同源）；weak ⇔ 有记录但不满足，或满足但证据薄（conf < 0.5）
- **D7 解释双模式**：默认确定性模板（数字 100% 来自 breakdown）；--llm-explain 走 LLM（Prompt 明令禁止自算数字）+ check_consistency 程序比对（解释中数字 ⊄ breakdown 派生集即拦截），LLM 失败降级模板
- **D9 E2 runner 物化**：画像按 soft_profile.e2_profile_id upsert；JD 按 jd_source job#N 直用（e2-001 的 v2-16 文本与库内 job#16 content_hash 相同 → 自动去重复用，零 LLM）；别名变体样本（e2-012）走 backfill_pending LLM 物化（1 次调用，content_hash 幂等）
- **影响**：Phase 7 落地（src/skillgap/match/ + eval/e2.py，E2 基线 pass 全指标过线）；已知限制（系统性低估 + 三组指标与标注同构的循环验证风险）见 PHASE_7_REVIEW.md

---

## 待议决策

无阻塞项。Phase 2 执行中如遇新决策点，按"先补 ADR/日志再动代码"纪律追加记录。
