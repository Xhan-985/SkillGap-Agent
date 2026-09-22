# API —— 接口契约（Phase 1 冻结）

> SkillGap Agent ｜ Phase 1 交付物
> 契约原则：**所有数值字段携带 `evidence_ref`（指向 JD/证据/快照记录）；错误区分"抽取失败"与"样本不足"，不静默降级；LLM 不出现在任何数值计算路径。**

---

## 0. 通用约定

- 基础路径：`/api`；内容类型 `application/json`
- **部署边界（红线）**：MVP 无账号体系、无鉴权，**仅限本地单用户部署（127.0.0.1 / 内网）**。任何公网部署前必须先加认证与速率限制——这是部署前提而非实现细节（2026-08-31 评审 H6 修复）
- 端点八要素（Method/Path/Request/Response/Error/同步/LLM/数据来源，需求第二十八节）：同步与 LLM 参见 §1 总表逐端点标注；数据来源在端点规格内标注
- 统一错误体：

```json
{ "error": { "code": "SAMPLE_INSUFFICIENT", "message": "当前切片样本量 12 < 30，不足以输出统计",
             "details": { "sample_size": 12, "threshold": 30 } } }
```

- 错误码枚举：`VALIDATION_ERROR` / `LLM_EXTRACTION_FAILED` / `LLM_TIMEOUT` / `SAMPLE_INSUFFICIENT` / `NOT_FOUND` / `RATE_LIMITED` / `UPSTREAM_ERROR`（外部 API）/ `DB_ERROR` / `QUARANTINED`
- 同步端点超时 30s（LLM 相关 60s）；异步端点返回 `202 + task_id`，状态查询 `GET /api/tasks/{task_id}`

---

## 1. 端点总表

| Method | Path | 功能 | 同步 | LLM | MVP | 实现（Phase 11 T3 后） |
|---|---|---|---|---|---|---|
| POST | /api/jd/analyze | JD 结构化分析 | ✅ | ✅（抽取） | M1 | ✅ Phase 10 |
| POST | /api/jd/contribute | 匿名贡献 JD 进市场数据集 | ❌ 异步 | ✅（抽取，管道内） | M3 | ⬜ Phase 11 T4（CLI 通道可用） |
| POST | /api/jd/import | CSV/JSON 批量导入 | ❌ 异步 | ✅（抽取，管道内） | M4 | 🔧 CLI 通道（C1 裁决） |
| POST | /api/ingest/adzuna | 拉取 Adzuna 海外岗位 | ❌ 异步 | ✅（抽取，管道内） | M4 | 🔧 CLI 通道（C1 裁决） |
| POST | /api/resumes/analyze | 简历 → 证据化画像 | ✅ | ✅（证据识别） | M5 | ✅ Phase 10 |
| GET | /api/candidates/{id}/profile | 画像查询 | ✅ | ❌ | M5 | ✅ Phase 10 |
| DELETE | /api/candidates/{id} | 删除画像 | ✅ | ❌ | M5 | ✅ Phase 10 |
| POST | /api/match | 匹配打分 | ✅ | 解释可选 | M6 | ✅ Phase 10 |
| GET | /api/candidates/{id}/gaps | Skill Gap | ✅ | ❌ | M7 | ✅ Phase 10 |
| POST | /api/recommendations | ROI 建议 | ✅ | 解释可选 | M9 | ✅ Phase 10 |
| GET | /api/market/skills | 技能频率统计 | ✅ | ❌ | M8 | ✅ Phase 10 |
| GET | /api/market/skills/{skill_id}/evidence | 频率溯源 | ✅ | ❌ | M8 | ✅ Phase 10 |
| GET | /api/quality/report | 数据质量报告 | ✅ | ❌ | M11 | ✅ Phase 11 T3 |
| DELETE | /api/contributions/{deletion_code} | 删除匿名贡献 | ✅ | ❌ | M3 | ✅ Phase 11 T3 |
| GET | /api/eval/results | 评测结果历史 | ✅ | ❌ | M11 | ✅ Phase 11 T3 |
| GET | /api/health | 健康检查 | ✅ | ❌ | — | ✅ Phase 10 |

> **实现状态说明（Phase 11 C1 裁决）**：16 端点 = 13 HTTP 实现 + 2 管理端点裁为 CLI 通道（jd/import、ingest/adzuna——管理操作，无鉴权 HTTP 暴露反而扩大攻击面，§0 本地单用户红线）+ 1 待实现（jd/contribute，T4：migration 005 task 表 + BackgroundTasks + §2.2 内嵌 `GET /api/tasks/{id}`）。

---

## 2. 端点规格

### 2.1 POST /api/jd/analyze（M1）

**Request**：`{ "jd_text": "string(50-20000)" }`
**说明**：分析是**无状态即时计算，默认不落库**；数据入库唯一通道为 `/api/jd/contribute`（须 consent=true）——避免产生未经同意的市场数据记录（2026-08-31 评审 B1 修复）。
**Response 200**：

```json
{ "job": { "title": "AI 应用开发工程师", "job_category": "ai_application_dev", "city": "北京", "market": "china", "language": "zh" },
  "core_skills":  [ { "skill_id": "rag", "importance": "must_have", "evidence_text": "熟悉 RAG 全链路技术…", "evidence_ref": "jd#L12" } ],
  "secondary_skills": [ … ],
  "soft_requirements": [ { "type": "experience", "value": "1-3年" } ],
  "extraction_meta": { "model": "…", "prompt_version": "…", "latency_ms": 2100 } }
```

**Error**：`VALIDATION_ERROR`（长度/为空）；`LLM_EXTRACTION_FAILED`（重试 2 次后 Schema 仍失败，**明示失败不降级**）；`LLM_TIMEOUT`。
**数据来源**：用户输入。**是否 LLM**：是（唯一受控抽取节点）。**soft_requirements 存储说明**：soft_requirements（经验年限/学历/语言）随 contribute 入库时写入 job.soft_requirements（DATA_MODEL §2.2），作为 Match 公式 experience_relevance 的 JD 侧输入。
**实现备注（Phase 10 落地）**：响应透传服务层超集（技能层额外含 `raw_name`/`importance`/`intensity`——`intensity` 为 JD 熟练度词，**可空**：JD 未写熟练度时为 null）；未配 `LLM_API_KEY` → 502 明示不静默；标题 `title` 可选透传。

### 2.2 POST /api/jd/contribute（M3）

**Request**：`{ "jd_text": "string", "consent": true, "source_hint": "boss|nowcoder|liepin|other" }`（consent=false 拒绝）
**Response 202**：`{ "task_id": "…", "message": "脱敏与去重处理中" }` → 完成后 `GET /api/tasks/{id}` 返回：

```json
{ "status": "completed", "job_id": 123, "deduplicated": false,
  "pii_redaction": { "rules_version": "v1", "hits": { "phone": 1, "email": 0 } },
  "deletion_code": "XXXX-XXXX（一次性展示，请自行保存）" }
```

**Error**：`VALIDATION_ERROR`；`QUARANTINED`（质检隔离，含原因）；重复时返回 `deduplicated: true` 与既有 job_id（不算错误）。
**数据来源**：用户主动提交（Tier B）。**LLM**：管道内抽取。**说明**：source_hint 仅作来源统计标签，系统不向该平台发起任何请求。
**实现备注（Phase 11 现状）**：HTTP 端点未实现（T4 计划：migration 005 task 表 + FastAPI BackgroundTasks + D5 deletion_code 一次性展示语义）。当前贡献通道由 CLI 承载：`skillgap contribute` / `skillgap delete-contribution`（PII 脱敏 + deletion_code 哈希存储，管道已全量落地）；配套的 §2.14 DELETE 端点已实现（T3）。

### 2.3 POST /api/jd/import（M4）

**Request**：`multipart/form-data`（CSV/JSON 文件，列规格见 DATA_MODEL §7）
**Response 202** → 导入报告：`{ "total": 300, "inserted": 271, "duplicates": 24, "rejected": 5, "quarantined": 0, "errors": [行级错误] }`
**Error**：`VALIDATION_ERROR`（文件格式/列缺失，**整批拒绝**）；行级错误不中断整批。
**数据来源**：社区贡献（Tier C）。
**实现备注（Phase 11 C1 裁决）**：不暴露 HTTP——批量导入属管理操作，无鉴权面不扩大攻击面；CLI 通道：`skillgap import --file <csv|json>`（批次报告落 ingest_batch 回归历史，行级错误不中断整批）。

### 2.4 POST /api/ingest/adzuna（M4，管理命令暴露端点）

**Request**：`{ "country": "gb", "query": "LLM OR RAG OR AI engineer", "max_results": 500 }`
**Response 202** → `{ "fetched": 500, "inserted": 412, "duplicates": 88, "attribution": "Jobs by Adzuna" }`
**Error**：`UPSTREAM_ERROR`（Adzuna 429/5xx，退避重试 3 次后失败）；`RATE_LIMITED`（本地额度守卫）。
**数据来源**：Adzuna 公开 API（Tier A，Global 专用）。**约束**：拉取结果 market=global，永不可入中国市场统计（DB 约束 + 服务层双保险）。
**实现备注（Phase 11 C1 裁决）**：不暴露 HTTP（理由同 §2.3）；CLI 通道：`skillgap ingest-adzuna`（默认 gb，本地额度守卫 250 req/day；**尚未首拉**——global N=0 灰态属预期）。

### 2.5 POST /api/resumes/analyze（M5）

**Request**：`{ "resume_text": "string", "candidate_id": "local-uuid?" }`（新用户自动创建）
**Response 200**：`{ "candidate_id": "…", "skills": [ { "skill_id": "rag", "level": 4, "confidence": 0.91, "evidences": [ { "type": "project_detail", "text": "pgvector+Hybrid Search+RRF+Rerank", "weight": 1.0 } ], "evidence_ref": "resume#L8" } ], "soft_profile": { "experience_years": { "value": 2, "evidence_text": "两年后端开发经验…" }, "education": { "value": "本科·软件工程", "evidence_text": "…" }, "languages": null } }`
**soft_profile 说明**：经验年限/学历/语言的证据化抽取（DATA_MODEL §2.7），作为 Match 公式 experience_relevance 的用户侧输入；无对应简历内容时字段为 null（公式按中性 0.5 处理，DATA_MODEL §4.3）。
**Error**：`VALIDATION_ERROR`；`LLM_EXTRACTION_FAILED`（证据识别失败——**部分失败策略**：未识别技能不出现，不伪造低置信技能）。
**说明**：简历原文仅本会话保留，不进任何市场数据。`evidence_ref` 为分析会话内的简历行号定位（`resume#L<n>`，尽力而为）——简历原文不落库，故 profile 查询（§2.6）返回的 evidence_ref 为 null；CLI `resume-analyze` 响应为契约超集（额外含 notices/extraction 元信息），FastAPI 层落地时按本契约裁剪。
**实现备注（Phase 10 落地）**：已按契约裁剪（剥 notices）；错误映射——`ResumeValidationError`→422 / `ExtractionFailed`→502（details.retries）/ `LLMError`→502 `LLM_TIMEOUT`（provider 层不区分超时与网络错误，details.cause 携带原始异常名保真）/ 不存在 candidate→404。

### 2.6 GET /api/candidates/{id}/profile ／ 2.7 DELETE /api/candidates/{id}

GET：画像 + 每技能证据链（即 2.5 响应结构）。DELETE：级联删除画像/证据/匹配结果；`204`。`NOT_FOUND`。

### 2.8 POST /api/match（M6）

**Request**：`{ "candidate_id": "…", "jd_text": "string（或 job_id 二选一）" }`
**Response 200**：

```json
{ "overall_score": 72, "scoring_version": "1.0.0",
  "breakdown": { "coverage": 0.68, "importance_coverage": 0.60, "evidence_quality": 0.81, "experience_relevance": 0.70 },
  "strong_skills":  [ { "skill_id": "python", "confidence": 0.92, "evidence_ref": "resume#L3" } ],
  "weak_skills":    [ { "skill_id": "docker", "confidence": 0.35, "note": "证据强度低" } ],
  "missing_skills": [ { "skill_id": "mcp", "required_importance": "must_have", "jd_evidence_ref": "jd#L7" } ],
  "explanation": "文本解释（可选 LLM 生成，数值仅由 breakdown 携带，UI 渲染）" }
```

**Error**：`VALIDATION_ERROR`；`NOT_FOUND`。**LLM**：分数计算**零 LLM**（CI 静态检查）；解释生成可选。
**数据来源**：candidate + job 表。
**实现备注**（Phase 7 落地，DECISION_LOG D-2026-09-03-14）：CLI `match-score --candidate-id N --job-id M [--llm-explain]` 为本契约载体；响应额外含 `neutral_flags`（§4.3 中性 0.5 维度清单，如 `no_must_have`/`no_matched_skills`/`soft_not_evaluable`）与 `invalid`（`no_skills`=JD 零技能）。三组为技能名数组；`strong/weak` 判定线 confidence ≥ 0.5（与 gap-v1 同源），满足 ⇔ 等级达标。解释默认确定性模板（数字 100% 来自 breakdown）；`--llm-explain` 走 LLM 生成但数字经程序比对（不一致即拦截降级）。经验相关性：真实库 JD `soft_requirements` 全空 → 恒中性 0.5（C1 裁决，回填需 E1 prompt 变更走 E1 门禁）。结果落 `match_result` 表留痕（重复评分多行历史）。
**实现备注**（Phase 10 落地，jd_text 模式 C4）：`POST /api/match` 支持 `jd_text`/`job_id` 二选一（缺一/双缺 → 422）。jd_text 模式 = LLM 无状态抽取 → 词表归一组装 reqs → 复用 `compute_match` 纯函数 → **不落库**（无 consent 不入库，B1）；与 job_id 模式对同一 JD **同分一致性测试锚定**（无第二套公式）。`explain=true` 走 LLM 叙事、数字不一致拦截降级为确定性模板；job_id 模式零 LLM（不因缺 key 502）。

### 2.9 GET /api/candidates/{id}/gaps（M7）

**Query**：`?job_id=123`（单岗模式）；或 `?category=ai_application_dev&market=china&min_freq=0.20`（类目聚合模式；job_id 与 category 二选一）
**Response 200**：
```json
{ "candidate_id": 1, "mode": "job|category", "job_id": 123,
  "gaps": [ { "skill_id": "mcp", "required_level": 4, "actual_level": 1, "gap": 3,
              "type": "genuine|transferable", "via": "java",
              "demand": { "frequency": 0.27, "sample_size": 201 }, "cost": "low" } ],
  "transferable": [ { "skill_id": "mcp", "via": "java", "note": "工程能力与基础编程范式可迁移" } ],
  "gap_version": "gap-v1" }
```
**判定依据**：required/actual_level 与 gap 由 DATA_MODEL §4.2 映射与 §4.4 规则计算（程度词→等级；confidence 不进 gap——H1 口径）；transferable 依据 skill_relation(relation_type=transferable_to) + parent（一层）+ 自身证据（confidence ≥0.5），via 报证据技能、note 取 relation.note。排序：gap 降序、同 gap 按 frequency 降序；demand/cost 为 Phase 8 ROI 公式的原料（本端点不计算 potential_gain）。
**实现备注**（Phase 10 落地）：`GET /api/candidates/{id}/gaps` 双模式已落地（job_id 与 category 二选一，缺/双传 → 422）。
**类目聚合规则**（DECISION_LOG D-2026-09-03-13）：类目内出现频次 ≥ min_freq（默认 0.20）的技能进入要求清单；required_level = 该技能类目内 must_have 行映射最大值（无 must_have 行取 2）；响应含 category_sample_size 与该市场最新快照引用（demand 溯源）。

### 2.10 POST /api/recommendations（M9）

**Request**：`{ "candidate_id": "…", "time_budget_days": 14, "market": "china" }`
**Response 200**：

```json
{ "priority_items": [
    { "priority": 1, "skill_id": "fastapi", "demand": { "frequency": 0.62, "sample_size": 240, "evidence_ref": "snapshot#881" },
      "gap": 3, "cost": "low", "potential_gain": 1.86,
      "rationale": "目标岗位需求较高；当前证据不足；学习成本相对低；补齐后可覆盖更多岗位" } ],
  "formula_version": "roi-v1", "project_suggestions": [ … ] }
```

**红线**：`potential_gain` 等数值 100% 公式计算（Demand×Gap÷Cost），rationale 由模板/LLM 生成但**不得引入公式外数字**。
**Error**：`SAMPLE_INSUFFICIENT`（所选市场样本不足时，demand 缺省并明示）。
**实现口径（Phase 8 落地，DECISION_LOG D-2026-09-04-15）**：demand 参照系 = market 全类目聚合（频次 ≥0.20 入清单、required 取 must_have 映射最大值、无 must 取 2）；demand 溯源最新快照 evidence_ref；N<30 → INSUFFICIENT_MARKET_DATA 拒推（ADR-008 守门）。time_budget_days（7/14/30）不影响 ROI 排序，仅过滤 project_suggestions（est_days ≤ budget）。Agent 叙事（agent-plan）数字经 check_consistency 程序比对，越界即 revise/降级模板。E3 基线（2026-09-04，china N=201 × 五画像）：nDCG@5=0.6497 pass / hit_rate@3=1.0 / coverage=0.95（eval_run #8）。
**实现备注**（Phase 10 落地，D2 双口径）：本端点为**决策侧**——N<30 拒推返回 422 `SAMPLE_INSUFFICIENT` 统一错误体；与 §2.11 market/skills 的**展示侧**（200 + `insufficient: true` 灰态）构成"同一守门规则、两种表达"（展示可看、决策拒推，Phase 8 冻结语义）。time_budget_days/market 词表外 → 422。

### 2.11 GET /api/market/skills（M8）

**Query**：`?market=china|global&category=&city=&window_start=&window_end=&min_sample=30`
**Response 200**：

```json
{ "market": "china", "window": { "start": "2026-08-01", "end": "2026-08-31" }, "sample_size": 240,
  "confidence": "medium",
  "source_distribution": { "tier_a": 0.32, "tier_b": 0.55, "tier_c": 0.13 },
  "skills": [ { "skill_id": "python", "frequency": 0.80, "jd_count": 192, "evidence_ref": "snapshot#881" } ] }
```

**Error**：`SAMPLE_INSUFFICIENT`（N<30：**这是正确行为而非故障**——返回 200 + `insufficient: true` 结构亦可，v1 冻结为 200 + 明示字段，避免前端当错误处理）。
**LLM**：禁止（统计纯 SQL）。
**实现备注**（Phase 10 落地，D3 裁剪）：服务层超集剥离——`canonical_name`→`skill_id`、`source_distribution` 聚合 tier_a/b/c 键、`stats_filter`/`method_version` 不外露；`evidence_ref` = 溯源端点 URI（percent-encode，前端可直接点击——D10）。参数校验：market 枚举、category 严格枚举（对齐 CLI choices + DB CHECK）、`min_sample≥1`、window 须成对（服务层静默忽略 → API 层 422 明示）。

### 2.12 GET /api/market/skills/{skill_id}/evidence

**Response 200**：`{ "skill_id": "python", "jd_refs": [ { "job_id": 1, "title": "…", "source_type": "user_submitted", "evidence_text": "精通 Python…", "source_url": null, "collected_at": "…" } ] }`——每个百分比的溯源底账。
**实现备注**（Phase 10 落地）：词表外技能 → 404 `NOT_FOUND`；底账 `jd_count` 与 §2.11 频率口径一致（一致性测试锚定，不漂移）。

### 2.13 GET /api/quality/report（M11）

**Response 200**：`{ "duplicate_rate": 0.08, "missing_field_rate": 0.01, "pii_detection": { "rules_version": "v1", "scan_count": 1200, "hit_rate": 0.12, "manual_audit_pass": true }, "invalid_jd_rate": 0.03, "skill_extraction_error_rate": 0.02, "computed_at": "…" }`
**实现备注（Phase 11 T3 落地）**：五指标结构已实现——批次三率（duplicate / invalid_jd / missing_field）由 ingest_batch 全历史聚合（分子分母口径与单批报告一致）+ 全库扫描两率 + PII 检测（`manual_audit_pass` 人工抽查后回填，未抽查时如实为 null）；服务层超集字段（batches_today / job_count / hit_total 等）不外露（D3 裁剪纪律）。当前真实值见 DATA.md §5（duplicate 1.94% / invalid 0.49% / missing 0）。

### 2.14 DELETE /api/contributions/{deletion_code}

哈希比对删除对应贡献（DATA_GOVERNANCE §3）。`204` / `NOT_FOUND`（code 错误或已删）。**错误不区分"不存在"与"已删除"**（防探测）。
**实现备注（Phase 11 T3 落地）**：哈希比对删除 + 级联（job_skill / deletion_code 行）；不存在与已删除返回**字节级一致**的 404 统一错误体（防探测测试锚定）；无路径格式校验——无效格式自然哈希不匹配，不暴露 code 有效性。

### 2.15 GET /api/eval/results ／ 2.16 GET /api/health

eval：评测历史列表（指标 + 版本三元组 + 差异摘要）。health：`{ "status": "ok", "db": true, "llm": "reachable" }`。
**实现备注（Phase 10 落地）**：§2.16 已实现——`db` 为真实探活（SELECT 1）；`llm` 字段报告 **key 配置状态**而非真实连通性（健康检查不触发付费 LLM 调用——诚实偏差，与契约 "reachable" 的差异如实记录）。
**实现备注（Phase 11 T3 落地）**：§2.15 已实现——响应 `{ "runs": [...] }`，每行含指标 + 版本三元组（dataset/prompt 为顶层列，scoring_version 自 metrics 提升）+ 与上一条的**差异摘要**（同版本三元组优先比较，跨版本明示"谨慎解读"——与 `eval-report` 单一口径复用同一实现）。

---

## 3. 错误处理与可观测性（需求第三十/三十一节落地）

| 错误类 | Timeout | Retry | Fallback | 日志 |
|---|---|---|---|---|
| Validation | 即拒 | — | — | WARN（含字段路径） |
| LLM Error | 60s | 2 次（携带校验错误反馈） | 明示失败（jd/analyze）或降级模板解释（match/recommend 的 explanation） | ERROR + model/prompt_version |
| Timeout（上游 API） | 10s | 指数退避 ≤3 | ingest 记 checkpoint 次日续 | WARN |
| Rate Limit | — | 退避（尊重 Retry-After） | 本地额度守卫前置拦截 | WARN |
| DB Error | 5s | 1 次 | 事务回滚 + 503 | ERROR + request_id |
| Invalid Data（管道） | — | — | quarantine 队列 | WARN + 行级详情 |

**可观测性最小集**（按实际复杂度裁剪，不过度设计）：Request ID 贯穿日志、LLM 调用记录 latency/token/model、导入/ingest 任务的结构化摘要。LangGraph 的 node/trace 观测在 Phase 8 引入 Agent 时再加。
