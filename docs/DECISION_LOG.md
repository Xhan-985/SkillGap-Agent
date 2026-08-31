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

---

## 待议决策（进入 Phase 2 前）

无阻塞项。Phase 2 执行中如遇新决策点，按"先补 ADR/日志再动代码"纪律追加记录。
