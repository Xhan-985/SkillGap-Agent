# DATA_COLLECTION —— 数据来源记录规范（Phase 2 交付物）

> SkillGap Agent ｜ 2026-08-31 ｜ 配合 data/collect_template.csv 使用
> 红线（DATA_GOVERNANCE §8）：禁止任何平台爬虫/绕过登录/模拟用户行为。本规范只覆盖合规通道。

## 1. 收集通道与字段要求

| 通道 | source_type / source_name | 必填字段 | 附加要求 |
|---|---|---|---|
| 公司官方招聘页摘录 | public_job_page / company_career_page | source_url、collected_at | 浏览→复制→当场记录 URL 与时间 |
| 用户粘贴贡献 | user_submitted / user_contribution | consent=market_analysis | 过 CLI `contribute`（PII 自动脱敏） |
| 社区批量 | csv_import / community_csv | 九字段 | 过同一管道 |
| 自建 Demo 批次 | dataset_builtin / demo_dataset | 九字段 + skills 标注 | 本规范主通道 |

每条强制九字段：source_type / source_name / source_url / collected_at /
submitted_at / content_hash（管道自动计算，收集时留空）/ license_or_usage_note /
consent_status / data_quality。

## 2. 模板列说明（data/collect_template.csv）

- `title`：岗位标题原文（必填，含岗位信号词）
- `raw_text`：JD 全文（50-20000 字符；直接复制粘贴，不做改写）
- `company / city / country / region`：可空
- `salary_min/max/currency`：可空；能识别则填（中国：月·元）
- `job_category`：可空（留空由规则归类）；手工指定必须取 8 枚举之一
- `soft_requirements`：JSON 数组，如 `[{"type":"experience","value":"1-3年","evidence_text":"..."}]`
- `skills`：JSON 数组——**每项 evidence_text 必须是 raw_text 原文片段**（管道会做字符串定位校验，不通过即 extraction_failed）
- `collected_at`：YYYY-MM-DD
- `consent_status`：公开页摘录填 `none`；用户贡献通道由 CLI 处理

## 3. 分批纪律（MVP §3）

- 目标 200-300 条，分 4-5 批，**每批 50 条后跑一次**：
  `skillgap import --file data/batch_N.csv` → `skillgap stats --market china` → `skillgap quality-report`
- 词表校准：频率统计与词表对照；新出现技能进 `new_skill_candidate`，人工周级裁决
  （更新 skills_v1.csv → taxonomy_version 注记 → 重新 `skillgap seed`）
- 止损线：2 周 <100 条 → 缩小到"AI 应用开发"单一切片（MVP §6）

## 4. 抽样核对（Phase 2 验收：抽样 20 条人工核对字段）

每批导入后从 `job` 表随机抽 20 条（`ORDER BY random() LIMIT 20`），逐条核对：
九字段完整、market=china、market_ambiguous 不为 true、skills 的 evidence_text
可在 raw_text 中定位。发现偏差 → 记入本文件 §6。

## 5. Adzuna（Global，另行操作）

`skillgap ingest-adzuna --country gb --query "LLM OR RAG OR AI engineer" --max-results 500`
- 免费层 250 req/day（本地额度守卫自动拦截超额）
- 仓库**不分发** Adzuna 数据；数据只存本地库
- 展示引用时必须带 "Jobs by Adzuna" 归属

## 6. 收集日志（执行时逐批追加）

| 批次 | 日期 | 条数 | 导入结果（inserted/dup/quarantine） | 抽样核对 | 备注 |
|---|---|---|---|---|---|
| （待填） | | | | | |
