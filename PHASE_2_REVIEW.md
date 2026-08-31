# PHASE_2_REVIEW —— Phase 2 完成自检（六维）

> 状态：**PASS WITH RISKS**（代码与管道全绿；风险 = 首批 200-300 条人工收集尚未开始 + Adzuna 真实拉取未执行——均为用户执行项，见 §3）
> 验收：ROADMAP Phase 2 六项验收逐项核验结果（见 §2 表）
> 日期：2026-08-31 ｜ 测试：81 passed（pytest 全量，PostgreSQL 经 docker compose）

## 1. 交付物清单（对照 ROADMAP Phase 2 产出）

- [x] PG Schema（全部约束）+ pgvector 预留表（不建索引）——migrations/001_init.sql，21 张表
- [x] Ingestion 管道 S1-S10（Adzuna/CSV/JSON/贡献/PII/去重/质检 quarantine）——src/skillgap/ingest/
- [x] E5 数据质量指标（批次报告）——src/skillgap/quality_metrics.py
- [x] 词表 v1 建档（skill/alias/relation 种子——评审 M3 关闭）——taxonomy/data/ + seed.py
- [x] 数据来源记录规范（DATA_COLLECTION.md）+ 收集模板（data/collect_template.csv）
- [x] ADR-010 + DECISION_LOG D-2026-08-31-10（SQL-first 持久层决议）
- [x] CLI 全家桶（db-upgrade/seed/import/ingest-adzuna/contribute/delete-contribution/quarantine-list/raw-cleanup/quality-report/stats）——src/skillgap/cli.py

## 2. 六项验收核验

| 验收项 | 结果 | 证据 |
|---|---|---|
| 导入报告完整（新增/重复/失败计数） | ✅ | CLI `import` 输出 + test_pipeline.py::test_run_batch_report_counts；ingest_batch 入库留回归历史 |
| PII 规则单测通过（含边界用例） | ✅ | test_pii.py 11 项（校验位/误报/防重叠/fail-closed） |
| Adzuna 入库 market=global 无污染 | ✅ | test_adzuna.py::test_fetch_adzuna_pipeline_integration + test_stats.py::test_market_separation（零混淆断言）；真实 API 拉取待用户配额执行 |
| 抽样 20 条人工核对字段 | ⏳ | DATA_COLLECTION.md §4 流程已交付；待首批真实数据导入后执行 |
| 频率统计空跑通（SQL 口径确定） | ✅ | test_stats.py 5 项全绿；STATS_FILTER 常量冻结（N<30 守门，ADR-008） |
| `docker compose up` 数据库就绪 | ✅ | Task 2 healthcheck；本地 dev 库已跑通 db-upgrade → seed → import → stats → quality-report 全链冒烟 |

## 3. 六维自检

### Product（解决什么）
数据管道可用：一条命令完成 CSV/JSON 导入与 Adzuna 拉取，批次报告给出新增/重复/隔离/失败计数；用户贡献通道（opt-in + PII 脱敏 + deletion_code 删除）闭环。200-300 条人工收集可以开跑（规范 + 模板 + 分批纪律已交付）。

### Engineering（过度设计？）
表只多不少：21 张表全部来自 DATA_MODEL §2 + 管道支撑表（raw_jobs/ingest_batch/ingest_checkpoint/ingest_request_log），无自加业务表。SQL-first（psycopg3 + 版本化 SQL 迁移，ADR-010），无 ORM。计划自检发现的死代码 `_stage_raw` 已删除。执行期对计划的修正均为 bug 修复（B1 三值逻辑、CSV 列错位、守门口径统一），无范围扩张。

### AI（LLM 滥用？）
本阶段零 LLM 依赖；S8 以 SkillExtractor 协议接口预留（ManualSkillExtractor 承载人工标注，LLM 实现属 Phase 3）。PII/去重/质检/统计全部确定性规则，可审计可回放。

### Data（真实可溯？）
来源九字段 DB 层 NOT NULL + CHECK 强制（B1 用 IS NOT DISTINCT FROM 堵住 NULL 放行）；content_hash 唯一约束 + 管道预检双层去重；市场分离双保险（data_source 覆盖 + public_api→global 断言）；统计口径以 SQL 常量冻结（B1 修复后的过滤条件），测试断言常量与冻结规格一致。

### Evaluation（可验证？）
E5 三项自动指标（duplicate_rate / invalid_jd_rate / skill_extraction_error_rate）+ 阈值表 + 全库扫描（missing_field_rate 应恒为 0）+ PII 命中聚合；批次历史入 ingest_batch 供回归。测试 81 项全绿（含市场零混淆、幂等重跑、fail-closed、防探测删除等验收红线用例）。

### Resume（可讲什么）
"我实现了带 PII 三层防线与 fail-closed 语义的合规数据管道：来源九字段 DB 强制、content_hash 双层去重、中国/全球市场分离双保险、统计口径以 SQL 常量冻结可复现，批次级数据质量指标（E5）入回归历史——81 项测试覆盖验收红线。"

## 4. 遗留与移交 Phase 3

- S8 LLM 实现（LLM Gateway + Structured Output + 重试）
- extraction_status=pending 的 job 抽取回填命令（user_submitted 无标注时置 pending）
- 英文程度词映射（评审 M1，Phase 3 冻结抽取 Schema 时一并）
- 首批 50 条收集与词表校准（用户执行，DATA_COLLECTION §3/§6 日志待填）
- Adzuna 真实拉取（用户配置 app_id/app_key 后运行 ingest-adzuna，遵守 250 req/day）
- 抽样 20 条人工核对（首批数据入库后执行并回填 DATA_COLLECTION §4）
