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

| Method | Path | 功能 | 同步 | LLM | MVP |
|---|---|---|---|---|---|
| POST | /api/jd/analyze | JD 结构化分析 | ✅ | ✅（抽取） | M1 |
| POST | /api/jd/contribute | 匿名贡献 JD 进市场数据集 | ❌ 异步 | ✅（抽取，管道内） | M3 |
| POST | /api/jd/import | CSV/JSON 批量导入 | ❌ 异步 | ✅（抽取，管道内） | M4 |
| POST | /api/ingest/adzuna | 拉取 Adzuna 海外岗位 | ❌ 异步 | ✅（抽取，管道内） | M4 |
| POST | /api/resumes/analyze | 简历 → 证据化画像 | ✅ | ✅（证据识别） | M5 |
| GET | /api/candidates/{id}/profile | 画像查询 | ✅ | ❌ | M5 |
| DELETE | /api/candidates/{id} | 删除画像 | ✅ | ❌ | M5 |
| POST | /api/match | 匹配打分 | ✅ | 解释可选 | M6 |
| GET | /api/candidates/{id}/gaps | Skill Gap | ✅ | ❌ | M7 |
| POST | /api/recommendations | ROI 建议 | ✅ | 解释可选 | M9 |
| GET | /api/market/skills | 技能频率统计 | ✅ | ❌ | M8 |
| GET | /api/market/skills/{skill_id}/evidence | 频率溯源 | ✅ | ❌ | M8 |
| GET | /api/quality/report | 数据质量报告 | ✅ | ❌ | M11 |
| DELETE | /api/contributions/{deletion_code} | 删除匿名贡献 | ✅ | ❌ | M3 |
| GET | /api/eval/results | 评测结果历史 | ✅ | ❌ | M11 |
| GET | /api/health | 健康检查 | ✅ | ❌ | — |

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

### 2.3 POST /api/jd/import（M4）

**Request**：`multipart/form-data`（CSV/JSON 文件，列规格见 DATA_MODEL §7）
**Response 202** → 导入报告：`{ "total": 300, "inserted": 271, "duplicates": 24, "rejected": 5, "quarantined": 0, "errors": [行级错误] }`
**Error**：`VALIDATION_ERROR`（文件格式/列缺失，**整批拒绝**）；行级错误不中断整批。
**数据来源**：社区贡献（Tier C）。

### 2.4 POST /api/ingest/adzuna（M4，管理命令暴露端点）

**Request**：`{ "country": "gb", "query": "LLM OR RAG OR AI engineer", "max_results": 500 }`
**Response 202** → `{ "fetched": 500, "inserted": 412, "duplicates": 88, "attribution": "Jobs by Adzuna" }`
**Error**：`UPSTREAM_ERROR`（Adzuna 429/5xx，退避重试 3 次后失败）；`RATE_LIMITED`（本地额度守卫）。
**数据来源**：Adzuna 公开 API（Tier A，Global 专用）。**约束**：拉取结果 market=global，永不可入中国市场统计（DB 约束 + 服务层双保险）。

### 2.5 POST /api/resumes/analyze（M5）

**Request**：`{ "resume_text": "string", "candidate_id": "local-uuid?" }`（新用户自动创建）
**Response 200**：`{ "candidate_id": "…", "skills": [ { "skill_id": "rag", "level": 4, "confidence": 0.91, "evidences": [ { "type": "project_detail", "text": "pgvector+Hybrid Search+RRF+Rerank", "weight": 1.0 } ], "evidence_ref": "resume#L8" } ], "soft_profile": { "experience_years": { "value": 2, "evidence_text": "两年后端开发经验…" }, "education": { "value": "本科·软件工程", "evidence_text": "…" }, "languages": null } }`
**soft_profile 说明**：经验年限/学历/语言的证据化抽取（DATA_MODEL §2.7），作为 Match 公式 experience_relevance 的用户侧输入；无对应简历内容时字段为 null（公式按中性 0.5 处理，DATA_MODEL §4.3）。
**Error**：`VALIDATION_ERROR`；`LLM_EXTRACTION_FAILED`（证据识别失败——**部分失败策略**：未识别技能不出现，不伪造低置信技能）。
**说明**：简历原文仅本会话保留，不进任何市场数据。

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

### 2.9 GET /api/candidates/{id}/gaps（M7）

**Query**：`?job_id=123`（或 `?category=ai_application_dev` 用市场聚合要求）
**Response 200**：`{ "gaps": [ { "skill_id": "mcp", "required_level": 4, "actual_level": 1, "gap": 3, "type": "genuine", "demand": "见 market 端点" } ], "transferable": [ { "skill_id": "java", "note": "与 Python 工程能力部分可迁移" } ] }`
**判定依据**：required/actual_level 与 gap 由 DATA_MODEL §4.2 映射与 §4.4 规则计算（程度词→等级；confidence 不进 gap）；transferable 依据 skill_relation(relation_type=transferable_to) + 关联技能证据（confidence ≥0.5）。

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

### 2.12 GET /api/market/skills/{skill_id}/evidence

**Response 200**：`{ "skill_id": "python", "jd_refs": [ { "job_id": 1, "title": "…", "source_type": "user_submitted", "evidence_text": "精通 Python…", "source_url": null, "collected_at": "…" } ] }`——每个百分比的溯源底账。

### 2.13 GET /api/quality/report（M11）

**Response 200**：`{ "duplicate_rate": 0.08, "missing_field_rate": 0.01, "pii_detection": { "rules_version": "v1", "scan_count": 1200, "hit_rate": 0.12, "manual_audit_pass": true }, "invalid_jd_rate": 0.03, "skill_extraction_error_rate": 0.02, "computed_at": "…" }`

### 2.14 DELETE /api/contributions/{deletion_code}

哈希比对删除对应贡献（DATA_GOVERNANCE §3）。`204` / `NOT_FOUND`（code 错误或已删）。**错误不区分"不存在"与"已删除"**（防探测）。

### 2.15 GET /api/eval/results ／ 2.16 GET /api/health

eval：评测历史列表（指标 + 版本三元组 + 差异摘要）。health：`{ "status": "ok", "db": true, "llm": "reachable" }`。

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
