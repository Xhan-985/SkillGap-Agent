# DATA —— 数据从哪来（面试三问之一）

> 本文回答：数据来源与信任分层、批次历史、统计口径、质量指标、事故与重建记录。
> 口径级文档：`DATA_PIPELINE.md`（S1-S12 管道分步）/ `DATA_MODEL.md`（表与字段）/ `DATA_GOVERNANCE.md`（合规与 PII）/ `STATS_METHOD.md`（统计口径）。

## 1. 三通道与信任分层（ADR-002）

| 通道 | source_name | Trust Tier | 市场 | 现状（2026-09-22） |
|---|---|---|---|---|
| 公开 API 拉取 | adzuna | tier_a | global | 代码就绪，**尚未拉取**（global N=0 灰态） |
| 公司官方招聘页人工摘录 | company_career_page | tier_a | china | 74 条（36.6%） |
| 招聘平台页人工摘录 | boss_zhipin | tier_b | china | 128 条（63.4%） |
| 用户 opt-in 匿名贡献 | user_contribution | tier_b | china | 端点 Phase 11 T4 待实现（CLI 通道可用） |
| CSV 批量导入 | community_csv | tier_c | — | CLI 通道（`skillgap import`） |

红线：**不爬虫**（ADR-001）——所有数据经人工摘录或用户主动提交，项目不建立在反爬对抗上。每条 job 记录带来源九字段（source_type / source_url / collected_at / content_hash 等，DB 层 NOT NULL + CHECK 强制）；`data_source` 注册表 6 条，集中管理许可 / 归属 / Tier / 条款核查日期（terms_checked_at）。

## 2. 当前库快照（2026-09-22）

- **202 条 active 岗位**（全 china；201 条批次导入 + 1 条 E2 评测物化），覆盖 20 城市
- **1518 行 job_skill**（其中 1512 行已回填证据向量 bge-m3 1024 维）
- **词表 v1.9：87 技能 + 288 别名**（+ 新词候选表机制：词表外技能进 new_skill_candidate 不静默丢弃）
- **market_snapshot #1**：N=202，confidence=high，method_version=s11-v1（append-only）
- **eval_run 4 条**（E1 warn / E2 pass / E3 pass / E2 事故中间态 block 留档）
- 类目分布：agent_dev 80 · ai_application_dev 62 · llm_fullstack 25 · other 23 · ai_platform 8 · 其余 4

## 3. 批次历史（ingest_batch，导入报告全量留痕）

| 批次 | 来源 | total | inserted | duplicates | quarantined |
|---|---|---|---|---|---|
| 1 | company_career_page | 50 | 50 | 0 | 0 |
| 2 | company_career_page（含平台页混合行） | 50 | 50 | 0 | 0 |
| 3 | boss_zhipin | 106 | 101 | 4 | 1 |

批次 CSV（`data/batch_1~3.csv`）**git 跟踪**——数据集可从仓库零 LLM 完整重建（§6 有实证）。批次 3 含数据清洗记录：删 7 条非技术岗混入、时薪/日薪折算月薪、质检词表补"评测"信号。

## 4. 统计口径（STATS_METHOD.md / s11-v1）

- 频率 = jd_count / N；N = 过滤后 active 岗位数（user_submitted 须 consent=market_analysis 才进统计）
- **样本量守门**：N<30 拒绝出数（ADR-008）——展示侧 200 + `insufficient: true` 灰态，决策侧（recommendations）422 拒推
- **市场强分离**：china / global 由 DB CHECK + 服务层断言双保险，海外数据永不可入中国市场统计
- 快照 append-only（`snapshot-create`），当前 #1 top：Python 0.658 / RAG 0.446 / Prompt Engineering 0.401 / Java 0.347 / AI Coding 0.272
- **溯源**：每个频率可经 `GET /api/market/skills/{skill}/evidence` 点开支撑 JD 底账（evidence_text 回原文）

## 5. 质量指标（E5，`GET /api/quality/report`）

当前值：duplicate_rate 1.94% / invalid_jd_rate 0.49% / missing_field_rate 0 / skill_extraction_error_rate 0；PII 规则 v1（scan_count / hit_rate 见端点返回）。批次三率由 ingest_batch 全历史聚合，口径与单批报告一致。

## 6. 2026-09-22 数据卷事故与重建（诚实记录）

误执行 `docker compose down -v` 删除开发卷 → DB 独有层丢失（llm_cache / eval_run 历史 14 条 / 候选人画像 / 向量列）。当日恢复（R1-R3）：

1. 批次 CSV 重导入 201 岗 + 1505 行 job_skill（**零 LLM**）；
2. backfill 11 + 画像重建（cid=1）+ rag-index 1512；
3. E1/E2/E3 重跑全部落在基线带内（F1 0.8644 / ρ 0.8277 / nDCG 0.6497）——评测结论对数据重建稳健。

顺带发现并修复 E2 评测集 id 引用漂移缺陷（`job#N` 直用易位 → 改内容寻址 content_hash，e90c76b）。历史 eval_run 数值存档于 `data/eval/*.json` 与 EVALUATION.md。全记录：DECISION_LOG D-2026-09-22-20。

## 7. 合规（DATA_GOVERNANCE.md）

- 无爬虫红线（ADR-001）；平台页人工摘录须带 source_url
- 贡献数据：PII 规则脱敏（版本化）+ 匿名 + deletion_code 可删除（防探测：不存在与已删除同响应 404）
- Adzuna：attribution 常驻展示（"Jobs by Adzuna"）+ 条款核查日期过期重查
- 中文 JD 无合法自动化数据源——这是本项目数据架构（人工摘录 + 用户贡献）的前提约束
