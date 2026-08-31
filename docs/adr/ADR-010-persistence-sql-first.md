# ADR-010: 持久层选型——psycopg3 + 版本化 SQL 迁移（无 ORM）

- 状态：已接受（2026-08-31，Phase 2）
- 关联：ADR-003（PostgreSQL）、ADR-005（确定性层）、DATA_MODEL §3

## Context
Phase 2 落地 PG Schema 与数据管道。需要决定：数据库访问方式与迁移方式。
本项目核心卖点是"数字可溯源、口径可复现"（ARCHITECTURE §2 三层分离），统计全部是 SQL（ADR-003）。

## Options
1. **SQL-first：psycopg3 + 手写 SQL + 版本化 .sql 迁移文件（无 ORM）**
2. SQLAlchemy ORM + Alembic
3. 轻量 SQL 查询构造器（如 pugsql）

## Decision
选 1。理由：① 统计/约束/口径全部以 SQL 为单一事实源，与"可审计可回放"哲学一致；
② 迁移文件即 Schema 文档，与 DATA_MODEL.md 一一对应，评审/面试可直接对照；
③ 依赖最少（单人项目，无 ORM 缓存/会话复杂度税）；
④ Pydantic 已承担输入校验（防腐层），ORM 的模型校验职责重叠。
httpx（Adzuna 连接器 HTTP 客户端）与 pydantic-settings（配置）一并纳入，均为最小依赖。

## Consequences
- 所有 SQL 集中在明确命名的模块中（db/stats/pipeline），禁止散落字符串拼接；
- 迁移通过 `skillgap db-upgrade`（schema_migrations 表）执行，可重复运行幂等；
- 后续 FastAPI 层（Phase 3+）同样走 psycopg + Pydantic，不引入 ORM。
