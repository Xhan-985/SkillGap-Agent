# ADR-003：为什么 PostgreSQL？

状态：**已接受（Phase 1 冻结）** ｜ 日期：2026-08-31 ｜ 前身：Phase 0 DESIGN_DECISIONS ADR-001（运行时选型部分）

## Context

频率统计是产品根基（Phase 0 研究结论），统计必须**可审计、可复现**——"这个 68% 来自哪 N 条 JD"要能随时重算验证。数据模型是关系型为主（Job↔Skill↔Candidate 多对多 + 聚合统计）。单开发者，需与用户既有技能栈（PostgreSQL/pgvector/Docker，见用户画像）协同。

## Options

| 选项 | Pros | Cons |
|---|---|---|
| **PostgreSQL** | 关系查询/聚合（频率统计全是 SQL）天然可审计；约束体系落地数据纪律（NOT NULL/CHECK/唯一索引）；pgvector 扩展路径（ADR-004）；事务保证导入幂等 | 需要独立服务（Docker Compose 解决） |
| SQLite | 零运维单文件 | 切片统计/并发导入/评测集管理会撞墙；展示层面弱；与 Docker 多服务形态不匹配 |
| MongoDB | 文档型灵活 | 核心负载是 Join 与聚合，文档型无优势且难做引用完整性 |
| MySQL | 可行 | 无 pgvector → Phase 8 若做 RAG 需引第二个数据库 |
| DuckDB/纯 Pandas | 分析强 | 无服务层持久化，与"数据透明可审计"冲突 |

## Decision

**PostgreSQL（Docker Compose 编排）。** 数据纪律全部下沉到 DB 层：来源九字段 NOT NULL + CHECK、content_hash 唯一索引、market 字段 + 统计强制 group by、status 过滤（只统计 active）。

## Consequences

- 正面：口径可复现（snapshot 记录 method_version）；约束即文档（数据纪律不靠自觉）；与技能栈协同（面试可深答）
- 负面：部署多一个服务（clone→run 由 Compose 抹平）；对非关系型载荷（raw 载荷）用 jsonb 兜底（够用）

## Reversibility

撤销成本：**低-中**（单体内换 SQLite 是局部改动，但约束体系需在应用层重写）。
复议触发条件：数据集 <100 条且确定无并发导入需求 → 可降级 SQLite 减少部署面。
