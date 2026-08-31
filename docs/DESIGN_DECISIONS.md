# DESIGN_DECISIONS —— 决策索引（Phase 1）

> SkillGap Agent ｜ Phase 1 交付物
> **ADR 已迁移至 `docs/adr/` 目录**（ROADMAP Phase 1 计划落地）。本文档保留：ADR 索引 + 决策总表 + 风险登记表。Phase 0 的 5 个 ADR 内容已并入新编号体系（映射关系见下）。

---

## 1. ADR 索引（docs/adr/）

| ADR | 主题 | 状态 | 前身映射 |
|---|---|---|---|
| [ADR-001](adr/ADR-001-no-crawler.md) | 为什么不爬招聘平台（红线） | 已接受 | Phase 0 ADR-004 |
| [ADR-002](adr/ADR-002-data-sources.md) | 为什么 Public API + Public Job Pages + User Submitted JD | 已接受 | Phase 0 ADR-004（扩展） |
| [ADR-003](adr/ADR-003-postgresql.md) | 为什么 PostgreSQL | 已接受 | Phase 0 ADR-001 |
| [ADR-004](adr/ADR-004-pgvector.md) | 为什么/为什么不 pgvector（表预留不建索引） | 已接受 | Phase 0 ADR-001（拆分） |
| [ADR-005](adr/ADR-005-deterministic-match-score.md) | 为什么 LLM 不负责最终 Match Score | 已接受 | Phase 0 ADR-002 |
| [ADR-006](adr/ADR-006-langgraph.md) | 为什么/为什么不 LangGraph（v1 无 Agent） | 已接受 | Phase 0 ADR-005 |
| [ADR-007](adr/ADR-007-evidence.md) | 为什么需要 Evidence | 已接受 | Phase 1 新增 |
| [ADR-008](adr/ADR-008-sample-size.md) | 为什么市场统计必须显示 Sample Size | 已接受 | Phase 1 新增 |
| [ADR-009](adr/ADR-009-skill-extraction.md) | 技能抽取：LLM Structured Output + Taxonomy | 已接受 | Phase 0 ADR-003 |

每个 ADR 统一结构：Context → Options（含 Pros/Cons）→ Decision → Consequences → Reversibility。

---

## 2. 决策总表

| 决策 | 默认方案 | 被拒备选 | 例外/复议条件 |
|---|---|---|---|
| 数据获取 | 三通道（Adzuna + 公开页面人工摘录 + 用户贡献）+ Tier A/B/C | 任何形式爬虫 | 官方授权数据源出现 → 增量接入（ADR-001/002） |
| 数据库 | PostgreSQL | SQLite/Mongo/MySQL | 数据集 <100 条且无并发 → 可降级（ADR-003） |
| pgvector | 表结构预留、不建索引 | 立即启用 / 完全不预留 | Phase 8 RAG 启用时建索引（ADR-004） |
| 智能分层 | 确定性计算 + LLM 解释（三层分离） | 端到端 LLM / 纯规则 / LLM 先行 | E3 显示规则排序持续劣于人工 → Agent 内混合生成（ADR-005） |
| Match Score | 四项确定性公式（权重 heuristic） | LLM 打分 | E2 校准后升版本（ADR-005） |
| Agent | v1 无；Phase 8 单 Agent LangGraph | 五 Agent / 多 Agent 自治 | 追问需求 >30% 提前 / <10% 延后（ADR-006） |
| 技能抽取 | LLM Structured Output + alias/ESCO 归一 | 词典 / 微调 NER | F1 <0.75 且 3 轮无改善 → 缩词表（ADR-009） |
| 市场统计 | 分市场（China/Global）+ 样本量守门 | 混合市场 / 隐藏 N | 仅阈值数值可复议（ADR-008） |

---

## 3. 风险登记表

| 风险 | 可能性 | 影响 | 缓解 | 复查信号 |
|---|---|---|---|---|
| 中国数据集积累不足 | 中 | 高（差异化根基失效） | MVP.md §6 止损线：缩小切片保深度 | 2 周 <100 条 |
| Adzuna 额度/条款变动 | 中 | 中（Global 统计受限） | 代码与数据分离；周级快照降频；terms_checked_at 过期重查 | 连续超额/条款更新 |
| 抽取质量不达标 | 中 | 高 | E1 阈值 + 3 轮迭代止损 | F1 持续 <0.75 |
| PII 漏检 | 低-中 | 高（合规与信任） | 规则版本化 + 抽查 + quarantine；E5 漏检率 ≥2% 即 Block | 每月抽样 |
| 范围蔓延 | 高 | 中 | MoSCoW 冻结清单 + 每功能引用 ADR | 任何"顺手加"提议 |
| LLM 成本失控 | 低 | 中 | content_hash 缓存 + 调用日志 | 月成本超预算线 |
| 同质化误判 | 低 | 高 | Phase 0 三份研究已系统排查；README 差异声明 | 新竞品出现 |
| 评测过拟合 | 中 | 中 | 评测集版本冻结 + held-out + 报告附 N | E1 升但线上反馈降 |
