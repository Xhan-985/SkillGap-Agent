-- 001_init.sql — SkillGap Agent Phase 2 Schema
-- 对照 docs/DATA_MODEL.md §2；约束对照 §3（B1/B2/B3 修复已包含）
CREATE EXTENSION IF NOT EXISTS vector;

-- §2.1 来源字典
CREATE TABLE data_source (
    id                   SERIAL PRIMARY KEY,
    source_type          TEXT NOT NULL CHECK (source_type IN ('public_api','public_job_page','user_submitted','csv_import','dataset_builtin')),
    source_name          TEXT NOT NULL UNIQUE,
    trust_tier           TEXT NOT NULL CHECK (trust_tier IN ('tier_a','tier_b','tier_c')),
    license_or_usage_note TEXT NOT NULL DEFAULT '',
    attribution_html     TEXT,
    covers_market        TEXT NOT NULL CHECK (covers_market IN ('china','global','both')),
    terms_checked_at     DATE
);

-- §2.3 公司
CREATE TABLE company (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    company_type TEXT CHECK (company_type IN ('big_tech','startup','ai_app','fintech','foreign','other')),
    country      TEXT
);

-- 管道支撑：S2 Raw Staging（原文暂存，7 天清理）
CREATE TABLE raw_jobs (
    id            SERIAL PRIMARY KEY,
    payload       JSONB NOT NULL,          -- RawRecord（PII 通道为脱敏后载荷）
    source_fields JSONB NOT NULL,          -- 来源九字段快照
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','done','quarantined','rejected','failed')),
    error         TEXT,                    -- 隔离/失败原因
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ
);

-- §2.2 岗位（来源九字段 NOT NULL + CHECK；content_hash 唯一；market 分离）
CREATE TABLE job (
    id               SERIAL PRIMARY KEY,
    title            TEXT NOT NULL,
    job_category     TEXT NOT NULL CHECK (job_category IN
                     ('ai_application_dev','agent_dev','llm_fullstack','mcp_dev','ai_platform','python_ai_dev','dify_dev','other')),
    company_id       INT REFERENCES company(id),
    city             TEXT,
    country          TEXT,
    region           TEXT,
    market           TEXT NOT NULL CHECK (market IN ('china','global')),
    language         TEXT NOT NULL CHECK (language IN ('zh','en')),
    salary_min       INT,
    salary_max       INT,
    salary_currency  TEXT,
    raw_text         TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('active','quarantine','extraction_failed','rejected')),
    source_id        INT NOT NULL REFERENCES data_source(id),
    source_type      TEXT NOT NULL CHECK (source_type IN ('public_api','public_job_page','user_submitted','csv_import','dataset_builtin')),
    source_url       TEXT,
    collected_at     TIMESTAMPTZ NOT NULL,
    submitted_at     TIMESTAMPTZ,
    content_hash     TEXT NOT NULL,
    consent_status   TEXT CHECK (consent_status IN ('none','market_analysis')),
    data_quality     TEXT NOT NULL CHECK (data_quality IN ('verified','auto_passed','human_reviewed','suspect')),
    soft_requirements JSONB,
    parsed_metadata  JSONB,
    UNIQUE (content_hash),
    CHECK (source_type <> 'public_job_page' OR source_url IS NOT NULL),
    -- B1：user_submitted 的 consent 必填；IS NOT DISTINCT FROM 使 NULL 也被拒（三值逻辑下 = 比较会放行 NULL）
    CHECK (source_type <> 'user_submitted' OR consent_status IS NOT DISTINCT FROM 'market_analysis')
);
CREATE INDEX ix_job_market_status ON job (market, status);
CREATE INDEX ix_job_source ON job (source_type, consent_status);

-- §2.4 技能（共享内核；parent 自引用——B2 修复）
CREATE TABLE skill (
    id             SERIAL PRIMARY KEY,
    esco_id        TEXT,
    canonical_name TEXT NOT NULL UNIQUE,
    category       TEXT NOT NULL CHECK (category IN ('agent_framework','retrieval','serving','engineering','language','data','soft')),
    parent_skill_id INT REFERENCES skill(id) ON DELETE SET NULL,
    learning_cost  TEXT NOT NULL CHECK (learning_cost IN ('low','mid','high')),
    description    TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE skill_relation (
    id                SERIAL PRIMARY KEY,
    skill_id          INT NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
    related_skill_id INT NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
    relation_type     TEXT NOT NULL CHECK (relation_type IN ('related','transferable_to')),
    note              TEXT,
    UNIQUE (skill_id, relation_type, related_skill_id),
    CHECK (skill_id <> related_skill_id)
);

-- §2.5 别名与新词候选
CREATE TABLE skill_alias (
    id       SERIAL PRIMARY KEY,
    skill_id INT NOT NULL REFERENCES skill(id) ON DELETE CASCADE,
    alias    TEXT NOT NULL UNIQUE,
    language TEXT NOT NULL CHECK (language IN ('zh','en'))
);

CREATE TABLE new_skill_candidate (
    id                 SERIAL PRIMARY KEY,
    raw_name           TEXT NOT NULL UNIQUE,
    first_seen_job_id  INT REFERENCES job(id) ON DELETE SET NULL,
    suggested_skill_id INT REFERENCES skill(id),
    status             TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','accepted','rejected')),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §2.6 岗位技能要求（证据 NOT NULL——Evidence Layer JD 侧）
CREATE TABLE job_skill (
    id                    SERIAL PRIMARY KEY,
    job_id                INT NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    skill_id              INT NOT NULL REFERENCES skill(id),
    importance            TEXT NOT NULL CHECK (importance IN ('must_have','nice_to_have')),
    intensity             TEXT CHECK (intensity IN ('精通','熟练','熟悉','了解')),
    evidence_text         TEXT NOT NULL,
    extraction_confidence NUMERIC,
    extracted_by          TEXT NOT NULL,   -- 'manual' 或 'llm:<model>/<prompt_version>'
    UNIQUE (job_id, skill_id)
);

-- §2.7 用户侧
CREATE TABLE candidate (
    id           SERIAL PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active  TIMESTAMPTZ NOT NULL DEFAULT now(),
    soft_profile JSONB
);

CREATE TABLE candidate_skill (
    id           SERIAL PRIMARY KEY,
    candidate_id INT NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
    skill_id     INT NOT NULL REFERENCES skill(id),
    level        INT NOT NULL CHECK (level BETWEEN 1 AND 5),
    confidence   NUMERIC NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    source_type  TEXT NOT NULL CHECK (source_type IN ('resume_text','manual','github')),
    UNIQUE (candidate_id, skill_id)
);

CREATE TABLE candidate_evidence (
    id                SERIAL PRIMARY KEY,
    candidate_skill_id INT NOT NULL REFERENCES candidate_skill(id) ON DELETE CASCADE,
    evidence_type     TEXT NOT NULL CHECK (evidence_type IN ('project_detail','project_desc','bare_claim','manual')),
    evidence_text     TEXT NOT NULL,
    weight            NUMERIC NOT NULL CHECK (weight IN (1.0, 0.6, 0.3))
);

-- §2.8 匹配结果
CREATE TABLE match_result (
    id              SERIAL PRIMARY KEY,
    candidate_id    INT NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
    job_id          INT NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    overall_score   NUMERIC NOT NULL,
    breakdown       JSONB NOT NULL,
    strong_skills   JSONB,
    weak_skills     JSONB,
    missing_skills  JSONB,
    explanation     TEXT,
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    scoring_version TEXT NOT NULL
);

-- §2.9 建议
CREATE TABLE recommendation (
    id                SERIAL PRIMARY KEY,
    candidate_id      INT NOT NULL REFERENCES candidate(id) ON DELETE CASCADE,
    time_budget_days  INT NOT NULL CHECK (time_budget_days IN (7, 14, 30)),
    priority_items    JSONB NOT NULL,
    potential_gain    NUMERIC NOT NULL,
    project_suggestions JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §2.10 市场统计快照
CREATE TABLE market_snapshot (
    id                  SERIAL PRIMARY KEY,
    scope               JSONB NOT NULL,   -- {market(必填), job_category?, city?, window?}
    sample_size         INT NOT NULL CHECK (sample_size >= 30),   -- ADR-008 守门
    skill_frequency     JSONB NOT NULL,
    source_distribution JSONB NOT NULL,
    confidence          TEXT NOT NULL CHECK (confidence IN ('high','medium','low')),
    data_window_start   DATE,
    data_window_end     DATE,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    method_version      TEXT NOT NULL
);

-- §2.11 评测样本（冻结快照副本）
CREATE TABLE evaluation_sample (
    id            SERIAL PRIMARY KEY,
    eval_type     TEXT NOT NULL CHECK (eval_type IN ('skill_extraction','matching','recommendation','data_quality')),
    input_payload JSONB NOT NULL,
    ground_truth  JSONB,
    annotator     TEXT,
    annotated_at  TIMESTAMPTZ,
    dataset_version TEXT NOT NULL
);

-- §2.12 贡献删除凭证（哈希存储防探测）
CREATE TABLE deletion_code (
    id         SERIAL PRIMARY KEY,
    job_id     INT NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    code_hash  TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- §2.13 pgvector 预留（不建索引——ADR-004）
CREATE TABLE jd_embedding (
    id         SERIAL PRIMARY KEY,
    job_id     INT NOT NULL REFERENCES job(id) ON DELETE CASCADE,
    model      TEXT NOT NULL,
    dim        INT NOT NULL,
    embedding  vector,                      -- 无 typmod：允许任意维度，但无法建索引（符合"不提前建索引"）
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (job_id, model)
);

-- E5 支撑：导入批次报告（指标入库进回归历史，EVALUATION_PLAN §5.2）
CREATE TABLE ingest_batch (
    id                SERIAL PRIMARY KEY,
    source_name       TEXT NOT NULL,
    source_type       TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,
    total             INT NOT NULL DEFAULT 0,
    inserted          INT NOT NULL DEFAULT 0,
    duplicates        INT NOT NULL DEFAULT 0,
    quarantined       INT NOT NULL DEFAULT 0,
    rejected          INT NOT NULL DEFAULT 0,
    extraction_failed INT NOT NULL DEFAULT 0,
    errors            JSONB
);

-- Adzuna 支撑：S1 checkpoint（429/5xx 次日续拉）+ 本地额度守卫（250 req/day）
CREATE TABLE ingest_checkpoint (
    id          SERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    scope_key   TEXT NOT NULL,
    last_page   INT NOT NULL DEFAULT 1,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_name, scope_key)
);

CREATE TABLE ingest_request_log (
    id           SERIAL PRIMARY KEY,
    source_name  TEXT NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status_code  INT
);
CREATE INDEX ix_request_log_day ON ingest_request_log (source_name, requested_at);
