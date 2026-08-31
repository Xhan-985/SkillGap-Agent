# Phase 2：数据模型落地 + 数据管道 + Demo Dataset 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地 PostgreSQL Schema（全部冻结约束）、实现 Ingestion 管道 S1-S10（Adzuna 连接器 + CSV/JSON 导入器 + 用户贡献通道 + PII 规则库 + 去重 + 质检 quarantine）、E5 数据质量批次报告、词表 v1 建档、频率统计空跑通（SQL 口径冻结）。

**Architecture:** 模块化单体（Phase 1 冻结，ARCHITECTURE §2）。Phase 2 只建 Ingestion Context + 数据层：CLI 驱动（FastAPI 层属后续 Phase），S8 技能抽取以 `SkillExtractor` 协议接口预留（Phase 3 接 LLM Gateway），本阶段用 `ManualSkillExtractor` 承载 Demo Dataset 的人工标注技能。持久层选型：**psycopg3 + 版本化 SQL 迁移文件（无 ORM）**——与"统计全是 SQL、口径可审计"的项目哲学一致（ADR-010）。

**Tech Stack:** Python 3.11+ / psycopg[binary] 3 / httpx / pydantic v2 + pydantic-settings / pytest / Docker Compose（pgvector/pgvector:pg16 + redis）

**规格来源（冻结文档，实现不得偏离）：**
- [DATA_MODEL.md](../DATA_MODEL.md)：§2 全部表结构、§3 完整性约束、§5 词表 v1、§7 Demo Dataset 规格
- [DATA_PIPELINE.md](../DATA_PIPELINE.md)：S1-S10 分步规格（输入/输出/失败处理/是否 LLM）
- [DATA_GOVERNANCE.md](../DATA_GOVERNANCE.md)：§2 来源九字段、§4 PII、§6 Adzuna 条款义务
- [MVP.md](../MVP.md)：§4 门禁 G1-G6
- [EVALUATION_PLAN.md](../EVALUATION_PLAN.md)：§5 E5 五指标与阈值
- [API.md](../API.md)：§2.2/2.3/2.4 响应结构（CLI 输出对齐该契约）
- [ROADMAP.md](../ROADMAP.md)：Phase 2 产出/验收 + 评审遗留 M3（skill_relation 种子数据本阶段补齐）

**验收标准（ROADMAP Phase 2）：** 导入报告完整（新增/重复/失败计数）；PII 规则单测通过（含边界用例）；Adzuna 拉取入库 market=global 无污染（mock 集成测试 + 用户真实拉取）；抽样 20 条人工核对字段；频率统计空跑通（SQL 口径确定）；`docker compose up` 数据库就绪。

**纪律红线：** 不写任何爬虫代码；Adzuna 数据不分发进仓库（仓库只有连接器代码）；LLM 零参与（本阶段无 LLM 依赖）；统计模块零 LLM 依赖。

---

## 0. 文件结构（File Structure）

```
SkillGap Agent/
├── pyproject.toml                    # 包定义 + 依赖 + skillgap CLI 入口
├── docker-compose.yml                # postgres(pgvector) + redis
├── .env.example                      # 环境变量模板
├── .gitignore
├── migrations/
│   └── 001_init.sql                  # 全部表 DDL（DATA_MODEL §2 全量 + 管道支撑表）
├── src/skillgap/
│   ├── __init__.py
│   ├── config.py                     # pydantic-settings 配置
│   ├── db.py                         # 连接 + SQL 迁移执行器（schema_migrations）
│   ├── models.py                     # Pydantic：SourceFields/RawRecord/SkillAnnotation/BatchReport
│   ├── cli.py                        # argparse 子命令（db/seed/ingest/import/contribute/quality/stats...）
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── sources.py                # data_source 注册表种子（五来源 + 条款摘要）
│   │   ├── pii.py                    # S4/S5 PII 规则库 v1（检测+脱敏，fail-closed）
│   │   ├── normalize.py              # S3 规范化（哈希规范化/语言/市场/薪资/岗位类）
│   │   ├── quality.py                # S7 质检（pass/quarantine/reject）
│   │   ├── extract.py                # S8 接口（SkillExtractor 协议 + ManualSkillExtractor）+ S9 归一
│   │   ├── pipeline.py               # S2-S10 编排 + BatchReport + ingest_batch 入库
│   │   ├── importer.py               # S1 CSV/JSON 导入器（行级错误不中断）
│   │   ├── adzuna.py                 # S1 Adzuna 连接器（重试/限额/checkpoint/attribution）
│   │   └── contribute.py             # S1 用户贡献通道（opt-in + PII 强制 + deletion_code）
│   ├── taxonomy/
│   │   ├── __init__.py
│   │   ├── seed.py                   # 词表 v1 建档（幂等）
│   │   └── data/
│   │       ├── skills_v1.csv         # 30 技能 + 类别 + 成本 + parent + 中英 alias
│   │       └── skill_relations_v1.csv# transferable_to/related 种子（评审 M3 关闭）
│   ├── quality_metrics.py            # E5：批次指标 + 全库扫描 + 报告聚合
│   └── stats.py                      # S11 空跑：分市场频率 SQL（口径冻结字符串常量）
├── data/
│   └── collect_template.csv          # Demo Dataset 收集模板（含 2 条示例行）
├── docs/
│   ├── adr/ADR-010-persistence-sql-first.md
│   ├── DATA_COLLECTION.md            # 数据来源记录规范（Phase 2 交付物）
│   └── plans/2026-08-31-phase2-data-pipeline.md  # 本计划
└── tests/
    ├── conftest.py                   # DB fixture（连不上自动 skip；自动建 skillgap_test 库）
    ├── test_pii.py                   # 纯单测
    ├── test_normalize.py             # 纯单测
    ├── test_quality.py               # 纯单测
    ├── test_extract.py               # 纯单测（alias 归一/证据定位）
    ├── test_models.py                # 纯单测
    ├── test_adzuna.py                # MockTransport 单测
    ├── test_importer.py              # 文件解析单测
    ├── test_schema.py                # 集成：约束（九字段/唯一/CHECK）
    ├── test_taxonomy.py              # 集成：种子幂等/唯一
    ├── test_pipeline.py              # 集成：S2-S10 端到端 + E5
    ├── test_contribute.py            # 集成：贡献/去重/删除
    └── test_stats.py                 # 集成：口径/守门/置信度
```

**职责边界：** `ingest/` 每个文件对应管道一个/一组步骤（可独立重跑）；`models.py` 是跨步骤的数据契约（防腐层内部 Schema）；`stats.py` 只读消费 job/job_skill（Phase 4 的 Market Context 雏形）；CLI 只是编排入口，无业务逻辑。

---

## Task 1: 项目骨架 + 依赖 + ADR-010

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `src/skillgap/__init__.py`, `src/skillgap/config.py`
- Create: `docs/adr/ADR-010-persistence-sql-first.md`
- Modify: `docs/DECISION_LOG.md`（追加 D-2026-08-31-10）

- [ ] **Step 1: 写 pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "skillgap-agent"
version = "0.1.0"
description = "SkillGap Agent - evidence-based skill decision system (data layer & ingestion)"
requires-python = ">=3.11"
dependencies = [
    "psycopg[binary]>=3.1",
    "httpx>=0.27",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
skillgap = "skillgap.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
skillgap = ["taxonomy/data/*.csv"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: 写 .gitignore / .env.example / config.py / __init__.py**

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.env
dist/
build/
*.egg-info/
```

`.env.example`:
```
# PostgreSQL（docker compose up -d postgres 后可用）
DATABASE_URL=postgresql://skillgap:skillgap@localhost:5432/skillgap
TEST_DATABASE_URL=postgresql://skillgap:skillgap@localhost:5432/skillgap_test

# Adzuna（用户自行注册获取；仓库不分发数据，DATA_GOVERNANCE §6）
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
ADZUNA_BASE_URL=https://api.adzuna.com/v1/api/jobs
ADZUNA_DAILY_QUOTA=250
```

`src/skillgap/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/skillgap/config.py`:
```python
"""全局配置（pydantic-settings，环境变量优先，支持 .env）。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://skillgap:skillgap@localhost:5432/skillgap"
    test_database_url: str = "postgresql://skillgap:skillgap@localhost:5432/skillgap_test"

    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_base_url: str = "https://api.adzuna.com/v1/api/jobs"
    adzuna_daily_quota: int = 250  # 免费层 250 req/day（DATA_GOVERNANCE §6，2026-08-31 核查）


settings = Settings()
```

- [ ] **Step 3: 写 ADR-010（新依赖纪律：先 ADR 后依赖）**

`docs/adr/ADR-010-persistence-sql-first.md`:
```markdown
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
```

- [ ] **Step 4: DECISION_LOG.md 追加一行**（文末按现有格式）：

```markdown
| D-2026-08-31-10 | 持久层选型：psycopg3 + SQL 迁移文件（无 ORM）；新增依赖 httpx/pydantic-settings | ADR-010 | Phase 2 启动 |
```

- [ ] **Step 5: 安装并验证**

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\python -c "import skillgap; print(skillgap.__version__)"
```
Expected: `0.1.0`

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml .gitignore .env.example src docs/adr/ADR-010-persistence-sql-first.md docs/DECISION_LOG.md
git commit -m "chore(phase2): project skeleton, deps, ADR-010 sql-first persistence"
```

---

## Task 2: Docker Compose（pgvector + redis）

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: 写 docker-compose.yml**

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16
    container_name: skillgap-postgres
    environment:
      POSTGRES_USER: skillgap
      POSTGRES_PASSWORD: skillgap
      POSTGRES_DB: skillgap
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U skillgap -d skillgap"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    container_name: skillgap-redis
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

- [ ] **Step 2: 启动并验证数据库就绪（ROADMAP 验收项）**

```powershell
docker compose up -d postgres redis
docker compose ps   # postgres 状态 healthy
```
Expected: `skillgap-postgres` 与 `skillgap-redis` 均运行，postgres healthy。

- [ ] **Step 3: Commit**

```powershell
git add docker-compose.yml
git commit -m "chore(phase2): docker compose with pgvector postgres and redis"
```

---

## Task 3: PG Schema DDL + 迁移执行器（S2 raw 表 + 全部 DATA_MODEL 表）

**Files:**
- Create: `migrations/001_init.sql`, `src/skillgap/db.py`
- Test: `tests/conftest.py`, `tests/test_schema.py`

- [ ] **Step 1: 写 migrations/001_init.sql（完整 DDL，逐表对照 DATA_MODEL §2）**

```sql
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
    CHECK (source_type <> 'user_submitted' OR consent_status = 'market_analysis')
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
    finished_at       TIMESTAMPTZ,
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
```

- [ ] **Step 2: 写 src/skillgap/db.py（连接 + 迁移执行器）**

```python
"""数据库连接与 SQL 迁移执行（ADR-010：版本化 .sql 文件，幂等可重放）。"""
from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import DictRow, dict_row

from skillgap.config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def connect(url: str | None = None) -> psycopg.Connection[DictRow]:
    return psycopg.connect(url or settings.database_url, row_factory=dict_row)


def upgrade(conn: psycopg.Connection) -> list[str]:
    """按文件名顺序应用未执行的迁移，返回本次应用的迁移名列表。"""
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        cur.execute("SELECT name FROM schema_migrations")
        applied = {row["name"] for row in cur.fetchall()}
    conn.commit()

    applied_now: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        applied_now.append(path.name)
    return applied_now


def ensure_database(admin_url: str, db_name: str) -> None:
    """测试辅助：不存在则创建数据库（连接到 postgres 库执行 CREATE DATABASE）。"""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{db_name}"')
```

- [ ] **Step 3: 写 tests/conftest.py（DB 连不上自动 skip，保证纯单测始终可跑）**

```python
from __future__ import annotations

import os

import psycopg
import pytest

from skillgap import db
from skillgap.config import settings
from skillgap.taxonomy.seed import seed_all

TEST_URL = os.environ.get("TEST_DATABASE_URL", settings.test_database_url)
ADMIN_URL = "postgresql://skillgap:skillgap@localhost:5432/postgres"


@pytest.fixture(scope="session")
def db_conn():
    try:
        db.ensure_database(ADMIN_URL, TEST_URL.rsplit("/", 1)[-1])
        conn = psycopg.connect(TEST_URL, row_factory=psycopg.rows.dict_row)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用（docker compose up -d postgres）")
    db.upgrade(conn)
    seed_all(conn)
    yield conn
    conn.close()


DATA_TABLES = [
    "job_skill", "new_skill_candidate", "deletion_code", "jd_embedding",
    "match_result", "recommendation", "candidate_evidence", "candidate_skill",
    "candidate", "job", "company", "raw_jobs", "ingest_batch",
    "ingest_checkpoint", "ingest_request_log", "market_snapshot",
    "evaluation_sample",
]


@pytest.fixture()
def clean_db(db_conn):
    """每个测试清空数据表（保留 skill/词表/data_source 种子）。"""
    with db_conn.cursor() as cur:
        cur.execute(
            f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE"
        )
    db_conn.commit()
    return db_conn
```

- [ ] **Step 4: 写 tests/test_schema.py（约束测试——验收"全部约束"）**

```python
"""Schema 约束测试：九字段/唯一/CHECK（DATA_MODEL §3 + 评审 B1）。"""
from datetime import datetime, timezone

import psycopg
import pytest

from skillgap.ingest.sources import DATA_SOURCES

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _source(clean_db, **over):
    row = dict(DATA_SOURCES[1])  # company_career_page（both 市场）
    row.update(over)
    with clean_db.cursor() as cur:
        cur.execute(
            """INSERT INTO data_source (source_type, source_name, trust_tier,
               license_or_usage_note, covers_market, terms_checked_at)
               VALUES (%(source_type)s, %(source_name)s, %(trust_tier)s,
               %(license_or_usage_note)s, %(covers_market)s, %(terms_checked_at)s)
               RETURNING id""",
            row,
        )
        return cur.fetchone()["id"]


def _job_kwargs(source_id, **over):
    kw = dict(
        title="AI 应用开发工程师", job_category="ai_application_dev",
        market="china", language="zh", raw_text="x" * 100, status="active",
        source_id=source_id, source_type="public_job_page",
        source_url="https://example.com/job/1", collected_at=NOW,
        content_hash="h1", data_quality="auto_passed",
    )
    kw.update(over)
    return kw


def _insert_job(clean_db, **kw):
    cols = ", ".join(kw.keys())
    phs = ", ".join(f"%({k})s" for k in kw)
    with clean_db.cursor() as cur:
        cur.execute(f"INSERT INTO job ({cols}) VALUES ({phs}) RETURNING id", kw)
        rid = cur.fetchone()["id"]
    clean_db.commit()
    return rid


def test_content_hash_unique(clean_db):
    sid = _source(clean_db)
    _insert_job(clean_db, **_job_kwargs(sid))
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_job(clean_db, **_job_kwargs(sid, title="另一个标题"))


def test_public_job_page_requires_url(clean_db):
    sid = _source(clean_db)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_job(clean_db, **_job_kwargs(sid, source_url=None))


def test_user_submitted_requires_market_analysis_consent(clean_db):
    sid = _source(clean_db, source_type="user_submitted", source_name="u1", covers_market="china")
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_job(clean_db, **_job_kwargs(
            sid, source_type="user_submitted", source_url=None, consent_status=None))
    # consent=none 同样被拒（B1：未授权贡献数据永不入库）
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_job(clean_db, **_job_kwargs(
            sid, source_type="user_submitted", source_url=None, consent_status="none"))
    # consent=market_analysis 通过
    jid = _insert_job(clean_db, **_job_kwargs(
        sid, source_type="user_submitted", source_url=None,
        consent_status="market_analysis", content_hash="h2"))
    assert jid > 0


def test_market_enum_restricted(clean_db):
    sid = _source(clean_db)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_job(clean_db, **_job_kwargs(sid, market="mixed"))


def test_collected_at_not_null(clean_db):
    sid = _source(clean_db)
    with pytest.raises(psycopg.errors.NotNullViolation):
        _insert_job(clean_db, **_job_kwargs(sid, collected_at=None))


def test_snapshot_requires_sample_size_30(clean_db):
    with pytest.raises(psycopg.errors.CheckViolation):
        with clean_db.cursor() as cur:
            cur.execute(
                "INSERT INTO market_snapshot (scope, sample_size, skill_frequency,"
                " source_distribution, confidence, method_version)"
                " VALUES ('{}'::jsonb, 29, '[]'::jsonb, '{}'::jsonb, 'low', 'v0')")
    clean_db.rollback()


def test_jd_embedding_accepts_vector_no_index(clean_db):
    sid = _source(clean_db)
    jid = _insert_job(clean_db, **_job_kwargs(sid))
    with clean_db.cursor() as cur:
        cur.execute(
            "INSERT INTO jd_embedding (job_id, model, dim, embedding)"
            " VALUES (%s, 'test-model', 3, %s::vector)", (jid, "[1,2,3]"))
    clean_db.commit()
```

- [ ] **Step 5: 先跑（seed 模块尚未存在，会失败）**，然后创建空的 taxonomy/seed.py 占位会导致 conftest 失败——顺序调整：先完成 Task 5 的 seed.py 再回来跑本测试。**执行顺序备注：Task 3 与 Task 5 的测试一起验证。**

- [ ] **Step 6: Commit**

```powershell
git add migrations/001_init.sql src/skillgap/db.py tests/conftest.py tests/test_schema.py
git commit -m "feat(phase2): pg schema ddl (all frozen constraints) + migration runner + schema tests"
```

---

## Task 4: Pydantic 数据契约（RawRecord / SourceFields / BatchReport）

**Files:**
- Create: `src/skillgap/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 写 tests/test_models.py**

```python
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from skillgap.models import RawRecord, SkillAnnotation, SourceFields

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def test_source_fields_requires_source_type():
    with pytest.raises(ValidationError):
        SourceFields(source_name="x", collected_at=NOW)


def test_raw_record_defaults():
    rec = RawRecord(
        title="AI 工程师", raw_text="岗位描述" * 30,
        source=SourceFields(
            source_type="public_job_page", source_name="company_career_page",
            collected_at=NOW),
    )
    assert rec.source.consent_status == "none"
    assert rec.source.data_quality == "auto_passed"
    assert rec.suggested_skills == []


def test_skill_annotation_importance_enum():
    with pytest.raises(ValidationError):
        SkillAnnotation(raw_name="RAG", importance="required", evidence_text="x")


def test_raw_record_rejects_bad_market_source():
    with pytest.raises(ValidationError):
        SourceFields(source_type="crawler", source_name="x", collected_at=NOW)
```

- [ ] **Step 2: 写 src/skillgap/models.py**

```python
"""管道内部数据契约（防腐层 Schema——DATA_PIPELINE S1 输出 RawRecord）。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

SourceTypeEnum = Literal[
    "public_api", "public_job_page", "user_submitted", "csv_import", "dataset_builtin"
]
MarketEnum = Literal["china", "global"]
LanguageEnum = Literal["zh", "en"]
ConsentEnum = Literal["none", "market_analysis"]
DataQualityEnum = Literal["verified", "auto_passed", "human_reviewed", "suspect"]
ImportanceEnum = Literal["must_have", "nice_to_have"]
IntensityEnum = Literal["精通", "熟练", "熟悉", "了解"]


class SourceFields(BaseModel):
    """来源九字段（DATA_GOVERNANCE §2）——每条 Job 强制。"""
    source_type: SourceTypeEnum
    source_name: str
    source_url: str | None = None
    collected_at: datetime
    submitted_at: datetime | None = None
    content_hash: str = ""          # 由管道 S6 计算
    license_or_usage_note: str = ""
    consent_status: ConsentEnum = "none"
    data_quality: DataQualityEnum = "auto_passed"


class SkillAnnotation(BaseModel):
    """S8 抽取输出的技能项（LLM 或人工标注共用同一 Schema）。"""
    raw_name: str
    importance: ImportanceEnum
    intensity: IntensityEnum | None = None
    evidence_text: str


class RawRecord(BaseModel):
    title: str
    raw_text: str
    company_name: str | None = None
    city: str | None = None
    country: str | None = None
    region: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    job_category: str | None = None    # 空 = S3 规则归类
    soft_requirements: list[dict] | None = None
    suggested_skills: list[SkillAnnotation] = Field(default_factory=list)
    source: SourceFields


class RowError(BaseModel):
    row: int
    stage: str
    message: str


class BatchReport(BaseModel):
    """导入/ingest/贡献批次报告（API §2.3 契约对齐）。"""
    source_name: str
    total: int = 0
    inserted: int = 0
    duplicates: int = 0
    quarantined: int = 0
    rejected: int = 0
    extraction_failed: int = 0
    errors: list[RowError] = Field(default_factory=list)
    attribution: str | None = None
```

- [ ] **Step 3: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_models.py -v
```
Expected: 4 passed

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/models.py tests/test_models.py
git commit -m "feat(phase2): pydantic pipeline data contracts"
```

---

## Task 5: PII 规则库 v1（S4 检测 + S5 脱敏，fail-closed）

**Files:**
- Create: `src/skillgap/ingest/pii.py`, `src/skillgap/ingest/__init__.py`
- Test: `tests/test_pii.py`

- [ ] **Step 1: 写 tests/test_pii.py（含边界用例——MVP M3 验收）**

```python
import pytest

from skillgap.ingest.pii import (
    PIIFinding, RedactionError, detect_pii, redact, PII_RULES_VERSION,
)


def test_detect_phone_basic_and_variants():
    text = "联系电话 13812345678，或 +86 15987654321 / 186-0000-1111"
    findings = detect_pii(text)
    phones = [f for f in findings if f.pii_type == "phone"]
    assert len(phones) == 3
    assert all(f.rule_id.startswith("v1:") for f in phones)


def test_detect_phone_not_matched_inside_long_digits():
    # 20 位连续数字不是手机号
    assert detect_pii("订单号 13812345678123456789") == [] or \
        all(f.pii_type != "phone" for f in detect_pii("订单号 13812345678123456789"))


def test_detect_email():
    findings = detect_pii("简历投递 hr@example.com 谢谢")
    assert any(f.pii_type == "email" for f in findings)


def test_detect_wechat_and_qq():
    text = "加微信 w_xiaoming123 或 QQ： 123456789"
    findings = detect_pii(text)
    assert any(f.pii_type == "wechat" for f in findings)
    assert any(f.pii_type == "qq" for f in findings)


def test_detect_id_card_with_valid_checksum():
    # 有效的 18 位身份证（校验位通过）
    text = "身份证号 11010519491231002X 请登记"
    findings = detect_pii(text)
    assert any(f.pii_type == "id_card" for f in findings)


def test_detect_id_card_invalid_checksum_not_flagged():
    # 18 位但校验位错误 → 不标记（降低误报）
    text = "编号 110105194912310021 请登记"
    assert all(f.pii_type != "id_card" for f in detect_pii(text))


def test_detect_contact_name():
    findings = detect_pii("联系人：王大力，联系电话见上")
    assert any(f.pii_type == "contact" for f in findings)


def test_redact_replaces_all_types():
    text = "联系张三 13812345678，邮箱 a@b.com，微信 abc_12345，QQ 12345678"
    redacted, report = redact(text, detect_pii(text))
    assert "[PHONE_REDACTED]" in redacted
    assert "[EMAIL_REDACTED]" in redacted
    assert "[WECHAT_REDACTED]" in redacted
    assert "[QQ_REDACTED]" in redacted
    assert report["rules_version"] == PII_RULES_VERSION
    assert report["hits"]["phone"] == 1


def test_redact_keeps_readability_and_text_length_reasonable():
    text = "负责 RAG 系统开发。手机 13812345678。要求熟悉 LangChain。"
    redacted, _ = redact(text, detect_pii(text))
    assert "RAG" in redacted and "LangChain" in redacted
    assert "13812345678" not in redacted


def test_redact_fail_closed_on_bad_span():
    bad = [PIIFinding(pii_type="phone", start=5, end=2,
                      matched="x", rule_id="v1:phone")]
    with pytest.raises(RedactionError):
        redact("normal text", bad)


def test_clean_text_yields_no_findings():
    text = "岗位要求：熟悉大模型应用开发，掌握 RAG 与 Agent 编排，3 年以上经验。"
    assert detect_pii(text) == []
```

- [ ] **Step 2: 写 src/skillgap/ingest/pii.py**

```python
"""S4/S5：PII 检测与脱敏（确定性正则规则库，版本化）。

诚实边界（DATA_GOVERNANCE §4）：不声称 100% 覆盖；
三层防线 = 规则（本模块）→ 人工抽查 → quarantine 复核。
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

PII_RULES_VERSION = "v1"


@dataclass(frozen=True)
class PIIFinding:
    pii_type: str
    start: int
    end: int
    matched: str
    rule_id: str


class RedactionError(Exception):
    """脱敏失败（fail-closed：整条拒绝进入市场数据集）。"""


REDACTION_MARKERS = {
    "phone": "[PHONE_REDACTED]",
    "email": "[EMAIL_REDACTED]",
    "wechat": "[WECHAT_REDACTED]",
    "qq": "[QQ_REDACTED]",
    "contact": "[CONTACT_REDACTED]",
    "id_card": "[ID_REDACTED]",
}

# 规则顺序影响重叠去留：先具体（长模式）后宽泛
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?86[\s-]?)?1[3-9]\d(?:[\s-]?\d){9}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
_WECHAT_RE = re.compile(
    r"(?:微信|wechat|WeChat|V信|vx|VX)\s*[:：]?\s*[A-Za-z][A-Za-z0-9_-]{5,19}")
_QQ_RE = re.compile(r"(?:扣扣|QQ|qq|Q群|q群)\s*[:：]?\s*(?<!\d)[1-9]\d{4,10}(?!\d)")
_CONTACT_RE = re.compile(
    r"(?:联系人|招聘负责人|简历接收人|HR|hr)\s*[:：]?\s*[\u4e00-\u9fa5]{2,4}")
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK_MAP = "10X98765432"


def _valid_id_card_checksum(s: str) -> bool:
    total = sum(int(s[i]) * _ID_WEIGHTS[i] for i in range(17))
    return _ID_CHECK_MAP[total % 11] == s[17].upper()


def detect_pii(text: str) -> list[PIIFinding]:
    """规则检测（S4）。返回按位置排序、互不重叠的命中列表。"""
    raw: list[PIIFinding] = []

    def add(pii_type: str, m: re.Match) -> None:
        raw.append(PIIFinding(pii_type, m.start(), m.end(), m.group(0),
                              f"{PII_RULES_VERSION}:{pii_type}"))

    for m in _ID_CARD_RE.finditer(text):
        if _valid_id_card_checksum(m.group(0)):
            add("id_card", m)
    for m in _PHONE_RE.finditer(text):
        add("phone", m)
    for m in _EMAIL_RE.finditer(text):
        add("email", m)
    for m in _WECHAT_RE.finditer(text):
        add("wechat", m)
    for m in _QQ_RE.finditer(text):
        add("qq", m)
    for m in _CONTACT_RE.finditer(text):
        add("contact", m)

    # 去重叠：保留先出现（更长/更具体的规则已在顺序上优先）
    findings: list[PIIFinding] = []
    covered_until = -1
    for f in sorted(raw, key=lambda x: (x.start, -(x.end - x.start))):
        if f.start >= covered_until:
            findings.append(f)
            covered_until = f.end
    return findings


def redact(text: str, findings: list[PIIFinding]) -> tuple[str, dict]:
    """替换为类型标记（S5）。位置非法即抛 RedactionError（fail-closed）。"""
    out: list[str] = []
    pos = 0
    for f in sorted(findings, key=lambda x: x.start):
        if f.start < pos or f.start >= f.end or f.end > len(text):
            raise RedactionError(f"非法 PII 跨度: {f}")
        out.append(text[pos:f.start])
        out.append(REDACTION_MARKERS[f.pii_type])
        pos = f.end
    out.append(text[pos:])
    hits = Counter(f.pii_type for f in findings)
    report = {"rules_version": PII_RULES_VERSION, "hits": dict(hits)}
    return "".join(out), report
```

- [ ] **Step 3: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_pii.py -v
```
Expected: 11 passed

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/ingest/__init__.py src/skillgap/ingest/pii.py tests/test_pii.py
git commit -m "feat(phase2): pii rules v1 (detection + fail-closed redaction)"
```

---

## Task 6: 规范化 + 去重 + 质检（S3 / S6 / S7）

**Files:**
- Create: `src/skillgap/ingest/normalize.py`, `src/skillgap/ingest/quality.py`
- Test: `tests/test_normalize.py`, `tests/test_quality.py`

- [ ] **Step 1: 写 tests/test_normalize.py**

```python
from skillgap.ingest.normalize import (
    canonicalize_for_hash, classify_job_category, content_hash,
    detect_language, determine_market, parse_salary_range,
)


def test_canonicalize_folds_case_width_space():
    a = "熟悉 ＲＡＧ 与　LangChain 编排"
    b = "熟悉 RAG 与 LangChain 编排"
    assert canonicalize_for_hash(a) == canonicalize_for_hash(b)


def test_content_hash_stable_across_formatting():
    a = "岗位：AI工程师。\n要求：熟悉RAG。\n"
    b = "岗位：AI工程师。 要求：熟悉rag "
    assert content_hash(a) == content_hash(b)


def test_content_hash_differs_for_different_text():
    assert content_hash("熟悉RAG") != content_hash("熟悉vLLM")


def test_detect_language():
    assert detect_language("负责大模型应用开发，熟悉RAG链路") == "zh"
    assert detect_language("We need an LLM engineer with RAG experience") == "en"
    assert detect_language("12345 67890") is None
    # 中文 JD 含英文技能词，主体语言仍是中文（S3 备注）
    assert detect_language("岗位要求：熟悉 RAG、LangChain、Prompt 工程，三年经验") == "zh"


def test_determine_market_by_source_then_language():
    assert determine_market("en", "global") == "global"   # Adzuna 来源权威
    assert determine_market("en", "china") == "china"
    assert determine_market("zh", "both") == "china"
    assert determine_market("en", "both") == "global"
    assert determine_market(None, "both") is None          # 歧义 → 上层标记


def test_parse_salary_range():
    assert parse_salary_range("薪资 15K-25K") == (15000, 25000)
    assert parse_salary_range("15k~25k·14薪") == (15000, 25000)
    assert parse_salary_range("15000-25000 元/月") == (15000, 25000)
    assert parse_salary_range("1.5万-2.5万") == (15000, 25000)
    assert parse_salary_range("面议") == (None, None)


def test_classify_job_category():
    assert classify_job_category("AI 应用开发工程师") == "ai_application_dev"
    assert classify_job_category("Agent 算法工程师") == "agent_dev"
    assert classify_job_category("LLM 全栈工程师") == "llm_fullstack"
    assert classify_job_category("MCP 开发工程师") == "mcp_dev"
    assert classify_job_category("Machine Learning Platform Engineer") == "ai_platform"
    assert classify_job_category("Python 后端开发") == "python_ai_dev"
    assert classify_job_category("Dify 工作流编排师") == "dify_dev"
    assert classify_job_category("运营专员") == "other"
```

- [ ] **Step 2: 写 src/skillgap/ingest/normalize.py**

```python
"""S3 规范化 + S6 哈希去重（全部确定性规则，无 LLM）。"""
from __future__ import annotations

import hashlib
import re
import unicodedata

_WS_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u4e00-\u9fa5]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def canonicalize_for_hash(text: str) -> str:
    """去重规范化：NFKC（全角→半角）→ casefold → 折叠空白。"""
    text = unicodedata.normalize("NFKC", text).casefold()
    return _WS_RE.sub(" ", text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(canonicalize_for_hash(text).encode("utf-8")).hexdigest()


def detect_language(text: str) -> str | None:
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    total = cjk + latin
    if total == 0:
        return None
    return "zh" if cjk / total >= 0.3 else "en"


def determine_market(language: str | None, covers_market: str) -> str | None:
    """市场判定：来源覆盖权威；both 时按主体语言；无法判定返回 None（上层标 ambiguous）。"""
    if covers_market in ("china", "global"):
        return covers_market
    if language == "zh":
        return "china"
    if language == "en":
        return "global"
    return None


_SALARY_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(万|[kK])?\s*[-~至到～]\s*(\d+(?:\.\d+)?)\s*(万|[kK])?")


def parse_salary_range(text: str) -> tuple[int | None, int | None]:
    m = _SALARY_RE.search(text)
    if not m:
        return None, None
    lo, hi = float(m.group(1)), float(m.group(3))
    unit = m.group(2) or m.group(4)
    if unit == "万":
        lo, hi = lo * 10000, hi * 10000
    elif unit in ("k", "K"):
        lo, hi = lo * 1000, hi * 1000
    else:  # 无单位：小数值按 K 处理
        if lo < 200 and hi < 200:
            lo, hi = lo * 1000, hi * 1000
    return int(lo), int(hi)


_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ai_application_dev": ["ai应用", "大模型应用", "llm应用", "ai工程师", "算法应用",
                           "ai产品", "aigc", "生成式"],
    "agent_dev": ["agent", "智能体", "multi-agent"],
    "llm_fullstack": ["全栈", "full stack", "fullstack"],
    "mcp_dev": ["mcp", "model context protocol"],
    "ai_platform": ["机器学习平台", "ml平台", "ai平台", "ai infra", "mlops",
                    "推理服务", "模型部署", "平台工程"],
    "python_ai_dev": ["python开发", "python工程师", "python后端", "django", "flask",
                      "fastapi"],
    "dify_dev": ["dify", "coze", "扣子", "工作流编排"],
}


def classify_job_category(title: str, text: str = "") -> str:
    """岗位类别词表 v1 规则归类（DATA_MODEL §5.1）。"""
    hay = f"{title}\n{text[:500]}".casefold()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(k in hay for k in keywords):
            return category
    return "other"
```

- [ ] **Step 3: 写 tests/test_quality.py（S7 质检规则）**

```python
from skillgap.ingest.quality import validate_jd

GOOD_TEXT = "岗位描述：" + "负责大模型应用开发与RAG链路优化。" * 10


def test_pass_normal_jd():
    v = validate_jd("AI 应用开发工程师", GOOD_TEXT)
    assert v.verdict == "pass"
    assert v.language == "zh"


def test_too_short_quarantined():
    v = validate_jd("AI 工程师", "太短")
    assert v.verdict == "quarantine"
    assert "length" in v.reasons


def test_too_long_quarantined():
    v = validate_jd("AI 工程师", "x" * 20001)
    assert v.verdict == "quarantine"
    assert "length" in v.reasons


def test_unidentifiable_language_quarantined():
    v = validate_jd("AI 工程师", "1234 5678 9012 " * 10)
    assert v.verdict == "quarantine"
    assert "language_unidentifiable" in v.reasons


def test_title_without_job_signal_quarantined():
    v = validate_jd("星辰大海", GOOD_TEXT)
    assert v.verdict == "quarantine"
    assert "title_no_job_signal" in v.reasons


def test_empty_title_quarantined():
    v = validate_jd("", GOOD_TEXT)
    assert v.verdict == "quarantine"


def test_spam_rejected():
    v = validate_jd("招聘专员", "日入五百，点击链接马上赚钱，加我微信了解详情" * 5)
    assert v.verdict == "reject"


def test_template_like_quarantined():
    text = ("岗位急招，速来岗位急招，速来\n") * 10
    v = validate_jd("招聘工程师", text)
    assert v.verdict == "quarantine"
```

- [ ] **Step 4: 写 src/skillgap/ingest/quality.py**

```python
"""S7 质检：pass / quarantine / reject（G4 有效性门禁）。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from skillgap.ingest.normalize import detect_language

MIN_LEN, MAX_LEN = 50, 20000

_JOB_SIGNAL = ["工程师", "开发", "研发", "技术", "算法", "实习", "经理", "架构师",
               "专员", "分析师", "scientist", "engineer", "developer", "manager",
               "ai", "人工智能", "大模型", "llm", "agent", "智能体", "rag",
               "后端", "前端", "全栈", "软件", "数据"]

_SPAM_MARKERS = ["刷单", "兼职日结", "点击链接", "稳赚", "日入", "带赚", "零门槛高薪"]


@dataclass
class QualityVerdict:
    verdict: str                     # pass / quarantine / reject
    language: str | None = None
    reasons: list[str] = field(default_factory=list)


def validate_jd(title: str, text: str) -> QualityVerdict:
    reasons: list[str] = []
    stripped = text.strip()

    if not (MIN_LEN <= len(stripped) <= MAX_LEN):
        reasons.append("length")
    language = detect_language(stripped)
    if language is None:
        reasons.append("language_unidentifiable")

    if not title or not title.strip():
        reasons.append("empty_title")
    else:
        title_fold = title.casefold()
        if not any(sig.casefold() in title_fold for sig in _JOB_SIGNAL):
            reasons.append("title_no_job_signal")

    if any(marker in stripped for marker in _SPAM_MARKERS):
        return QualityVerdict("reject", language, reasons + ["spam"])

    # 模板文本：行数足够且重复率极高
    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    if len(lines) >= 8 and len(set(lines)) / len(lines) < 0.5:
        reasons.append("template_like")

    if reasons:
        return QualityVerdict("quarantine", language, reasons)
    return QualityVerdict("pass", language, reasons)
```

- [ ] **Step 5: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_normalize.py tests/test_quality.py -v
```
Expected: 全部 passed

- [ ] **Step 6: Commit**

```powershell
git add src/skillgap/ingest/normalize.py src/skillgap/ingest/quality.py tests/test_normalize.py tests/test_quality.py
git commit -m "feat(phase2): s3 normalization, s6 content hash dedup, s7 quality gates"
```

---

## Task 7: 来源注册表 + 词表 v1 建档（含 skill_relation 种子——评审 M3 关闭）

**Files:**
- Create: `src/skillgap/ingest/sources.py`, `src/skillgap/taxonomy/__init__.py`,
  `src/skillgap/taxonomy/seed.py`, `src/skillgap/taxonomy/data/skills_v1.csv`,
  `src/skillgap/taxonomy/data/skill_relations_v1.csv`
- Test: `tests/test_taxonomy.py`

- [ ] **Step 1: 写 src/skillgap/ingest/sources.py（data_source 注册表，条款摘要来自 DATA_GOVERNANCE §6）**

```python
"""data_source 注册表种子（五来源，Trust Model 见 ADR-002）。"""
from __future__ import annotations

from datetime import date

DATA_SOURCES = [
    dict(
        source_type="public_api", source_name="adzuna", trust_tier="tier_a",
        license_or_usage_note=(
            "Adzuna ToS（核查 2026-08-31）：展示需带 'Jobs by Adzuna' 归属并链接 "
            "adzuna.co.uk；禁止以原始或聚合形式再分发；免费层 25 req/min、250 req/day"),
        attribution_html='<a href="https://www.adzuna.co.uk">Jobs by Adzuna</a>',
        covers_market="global", terms_checked_at=date(2026, 8, 31),
    ),
    dict(
        source_type="public_job_page", source_name="company_career_page",
        trust_tier="tier_a",
        license_or_usage_note=(
            "公司官方招聘页人工摘录（记录 source_url）；仅本项目内部统计用途，不分发原文"),
        attribution_html=None, covers_market="both",
        terms_checked_at=date(2026, 8, 31),
    ),
    dict(
        source_type="user_submitted", source_name="user_contribution",
        trust_tier="tier_b",
        license_or_usage_note=(
            "用户 opt-in 匿名贡献（consent=market_analysis）；PII 脱敏后入库；"
            "deletion_code 支持删除（DATA_GOVERNANCE §3）"),
        attribution_html=None, covers_market="china",
        terms_checked_at=date(2026, 8, 31),
    ),
    dict(
        source_type="csv_import", source_name="community_csv", trust_tier="tier_c",
        license_or_usage_note="社区 CSV/JSON 批量贡献；过同一管道（PII/去重/质检）",
        attribution_html=None, covers_market="china",
        terms_checked_at=date(2026, 8, 31),
    ),
    dict(
        source_type="dataset_builtin", source_name="demo_dataset", trust_tier="tier_a",
        license_or_usage_note=(
            "项目自建 Demo Dataset（人工合规摘录，来源九字段完整；"
            "每批 50 条后校准词表，MVP §3）"),
        attribution_html=None, covers_market="china",
        terms_checked_at=date(2026, 8, 31),
    ),
]


def seed_sources(conn) -> None:
    with conn.cursor() as cur:
        for row in DATA_SOURCES:
            cur.execute(
                """INSERT INTO data_source (source_type, source_name, trust_tier,
                   license_or_usage_note, attribution_html, covers_market,
                   terms_checked_at)
                   VALUES (%(source_type)s, %(source_name)s, %(trust_tier)s,
                   %(license_or_usage_note)s, %(attribution_html)s,
                   %(covers_market)s, %(terms_checked_at)s)
                   ON CONFLICT (source_name) DO UPDATE SET
                   license_or_usage_note = EXCLUDED.license_or_usage_note,
                   attribution_html = EXCLUDED.attribution_html,
                   terms_checked_at = EXCLUDED.terms_checked_at""",
                row,
            )
    conn.commit()


def get_source(conn, source_name: str) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM data_source WHERE source_name = %s", (source_name,))
        row = cur.fetchone()
    if row is None:
        raise KeyError(f"未注册的数据来源: {source_name}（先运行 skillgap seed）")
    return row
```

- [ ] **Step 2: 写词表 CSV（DATA_MODEL §5.2 的 30 技能 + 类别/成本/parent/中英 alias）**

`src/skillgap/taxonomy/data/skills_v1.csv`（列：canonical_name,category,parent,learning_cost,esco_id,aliases_zh,aliases_en,description；alias 用 `|` 分隔，`-` 表示空）：

```csv
Python,language,-,low,-,派森|Python语言,python|python3|py,Python 编程语言
Java,language,-,mid,-,爪哇|Java语言,java|jdk,Java 编程语言
LLM 应用开发,engineering,-,mid,-,大模型应用开发|LLM应用开发,llm application|llm app,LLM 应用开发总体能力
LangChain,agent_framework,-,mid,-,兰链,langchain|lang chain,LLM 应用编排框架
LangGraph,agent_framework,LangChain,mid,-,-,langgraph|lang graph,图结构 Agent 编排
AutoGen,agent_framework,-,mid,-,-,autogen,多 Agent 对话框架
CrewAI,agent_framework,-,low,-,-,crewai|crew ai,角色分工 Agent 框架
RAG,retrieval,-,mid,-,检索增强生成|RAG技术,rag|retrieval augmented generation,检索增强生成
Prompt Engineering,engineering,-,low,-,提示词工程|提示工程,prompt engineering|prompting,提示词工程
MCP,engineering,-,mid,-,模型上下文协议,model context protocol|mcp,Model Context Protocol
Dify,engineering,-,low,-,迪飞,dify,Dify 低代码平台
FastAPI,engineering,-,low,-,-,fastapi|fast api,Python Web 框架
Docker,engineering,-,low,-,容器技术|docker容器,docker|docker compose,容器化
Kubernetes,engineering,-,high,-,K8s|容器编排,kubernetes|k8s,容器编排
PostgreSQL,data,-,low,-,PG数据库|postgres数据库,postgresql|postgres|psql,关系型数据库
MySQL,data,-,low,-,-,mysql,关系型数据库
Redis,data,-,mid,-,-,redis,缓存与消息队列
pgvector,retrieval,-,mid,-,PG向量插件,pgvector|pg vector,PostgreSQL 向量扩展
Milvus,retrieval,-,high,-,向量数据库,milvus,向量数据库
Chroma,retrieval,-,low,-,向量数据库,chroma|chromadb,嵌入式向量数据库
Qdrant,retrieval,-,mid,-,向量数据库,qdrant,向量数据库
Neo4j,retrieval,-,mid,-,图数据库,neo4j,图数据库
SFT/LoRA,serving,-,high,-,微调|大模型微调|LoRA微调,sft|lora|fine-tuning|finetuning,监督微调与低秩适配
vLLM,serving,-,high,-,推理引擎,vllm|v-llm,高吞吐推理服务
Evaluation（LLM 评测）,engineering,-,mid,-,LLM评测|大模型评测|评测体系,llm evaluation|eval,LLM 评测方法
多模态,serving,-,high,-,多模态大模型,multimodal|multi-modal,多模态模型开发
Function Calling,agent_framework,-,low,-,函数调用|工具调用,function calling|tool calling,函数调用能力
ReAct,agent_framework,-,low,-,ReAct模式,react,推理+行动范式
上下文管理,retrieval,-,mid,-,长上下文|context管理,context management|long context,上下文窗口管理
AI Coding,engineering,-,low,-,AI编程|AI辅助编程,ai coding|cursor|copilot,AI 辅助编程
```

`src/skillgap/taxonomy/data/skill_relations_v1.csv`（列：skill,related_skill,relation_type,note）：

```csv
Java,Python,transferable_to,工程能力与基础编程范式可迁移
Python,Java,transferable_to,工程能力与基础编程范式可迁移
MySQL,PostgreSQL,transferable_to,SQL 与关系型数据库经验可迁移
PostgreSQL,MySQL,transferable_to,SQL 与关系型数据库经验可迁移
LangChain,LangGraph,related,同属 LangChain 生态编排框架
LangGraph,LangChain,related,同属 LangChain 生态编排框架
Milvus,Chroma,related,同为向量数据库
Chroma,Milvus,related,同为向量数据库
Chroma,Qdrant,related,同为向量数据库
Qdrant,Chroma,related,同为向量数据库
pgvector,Chroma,related,同为向量检索方案
Chroma,pgvector,related,同为向量检索方案
```

- [ ] **Step 3: 写 src/skillgap/taxonomy/seed.py（幂等建档）**

```python
"""词表 v1 正式建档（skill / skill_alias / skill_relation 种子；幂等可重跑）。"""
from __future__ import annotations

import csv
from importlib import resources

from skillgap.ingest.sources import seed_sources


def _read_csv(name: str) -> list[dict]:
    text = resources.files("skillgap.taxonomy").joinpath(f"data/{name}").read_text(
        encoding="utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def seed_taxonomy(conn) -> dict:
    """返回 {"skills": n, "aliases": n, "relations": n}（含已存在的总数）。"""
    skills = _read_csv("skills_v1.csv")
    name_to_id: dict[str, int] = {}

    with conn.cursor() as cur:
        # 第一遍：无 parent 插入（幂等）
        for row in skills:
            cur.execute(
                """INSERT INTO skill (canonical_name, category, learning_cost,
                   esco_id, description)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (canonical_name) DO UPDATE SET
                     category = EXCLUDED.category,
                     learning_cost = EXCLUDED.learning_cost,
                     description = EXCLUDED.description
                   RETURNING id""",
                (row["canonical_name"], row["category"], row["learning_cost"],
                 None if row["esco_id"] == "-" else row["esco_id"],
                 row["description"] or None),
            )
            name_to_id[row["canonical_name"]] = cur.fetchone()["id"]
        # 第二遍：parent 关联（B2：Taxonomy 层级）
        for row in skills:
            if row["parent"] != "-":
                cur.execute(
                    "UPDATE skill SET parent_skill_id = %s WHERE id = %s",
                    (name_to_id[row["parent"]], name_to_id[row["canonical_name"]]))
        # 别名（全局唯一，幂等跳过）
        for row in skills:
            skill_id = name_to_id[row["canonical_name"]]
            for alias in filter(None, row["aliases_zh"].split("|")):
                cur.execute(
                    """INSERT INTO skill_alias (skill_id, alias, language)
                       VALUES (%s, %s, 'zh') ON CONFLICT (alias) DO NOTHING""",
                    (skill_id, alias.strip()))
            for alias in filter(None, row["aliases_en"].split("|")):
                cur.execute(
                    """INSERT INTO skill_alias (skill_id, alias, language)
                       VALUES (%s, %s, 'en') ON CONFLICT (alias) DO NOTHING""",
                    (skill_id, alias.strip()))
        # 关系（对称双行，评审 M3 关闭）
        for row in _read_csv("skill_relations_v1.csv"):
            cur.execute(
                """INSERT INTO skill_relation (skill_id, related_skill_id,
                   relation_type, note)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (skill_id, relation_type, related_skill_id)
                   DO UPDATE SET note = EXCLUDED.note""",
                (name_to_id[row["skill"]], name_to_id[row["related_skill"]],
                 row["relation_type"], row["note"]))
        cur.execute("SELECT count(*) AS c FROM skill")
        n_skills = cur.fetchone()["c"]
        cur.execute("SELECT count(*) AS c FROM skill_alias")
        n_alias = cur.fetchone()["c"]
        cur.execute("SELECT count(*) AS c FROM skill_relation")
        n_rel = cur.fetchone()["c"]
    conn.commit()
    return {"skills": n_skills, "aliases": n_alias, "relations": n_rel}


def seed_all(conn) -> None:
    """CLI/测试统一入口：来源注册表 + 词表。"""
    seed_sources(conn)
    seed_taxonomy(conn)
```

`src/skillgap/taxonomy/__init__.py` 与 `src/skillgap/ingest/__init__.py`（若尚未创建）留空。

- [ ] **Step 4: 写 tests/test_taxonomy.py**

```python
from skillgap.ingest.sources import get_source
from skillgap.taxonomy.seed import seed_all, seed_taxonomy


def test_seed_idempotent(clean_db):
    a = seed_taxonomy(clean_db)
    b = seed_taxonomy(clean_db)
    assert a == b                      # 重跑不翻倍
    assert a["skills"] == 30
    assert a["relations"] == 12
    assert a["aliases"] > 60


def test_seed_all_registers_sources(clean_db):
    seed_all(clean_db)
    az = get_source(clean_db, "adzuna")
    assert az["covers_market"] == "global"
    assert az["trust_tier"] == "tier_a"
    assert "Jobs by Adzuna" in az["attribution_html"]


def test_parent_link_exists(clean_db):
    seed_taxonomy(clean_db)
    with clean_db.cursor() as cur:
        cur.execute(
            """SELECT p.canonical_name AS parent, c.canonical_name AS child
               FROM skill c JOIN skill p ON c.parent_skill_id = p.id""")
        pairs = {(r["parent"], r["child"]) for r in cur.fetchall()}
    assert ("LangChain", "LangGraph") in pairs


def test_transferable_relation_symmetric(clean_db):
    seed_taxonomy(clean_db)
    with clean_db.cursor() as cur:
        cur.execute(
            """SELECT s1.canonical_name AS a, s2.canonical_name AS b
               FROM skill_relation r
               JOIN skill s1 ON r.skill_id = s1.id
               JOIN skill s2 ON r.related_skill_id = s2.id
               WHERE r.relation_type = 'transferable_to'""")
        pairs = {(r["a"], r["b"]) for r in cur.fetchall()}
    assert ("Java", "Python") in pairs and ("Python", "Java") in pairs
```

- [ ] **Step 5: 运行（连同 Task 3 的 schema 测试）**

```powershell
.\.venv\Scripts\pytest tests/test_schema.py tests/test_taxonomy.py -v
```
Expected: schema 7 passed + taxonomy 4 passed（需 docker postgres 已启动）

- [ ] **Step 6: Commit**

```powershell
git add src/skillgap/ingest/sources.py src/skillgap/taxonomy tests/test_taxonomy.py
git commit -m "feat(phase2): data source registry + taxonomy v1 seed (skills/aliases/relations)"
```

---

## Task 8: S8 抽取接口 + S9 归一（手工标注通道，LLM Phase 3 接入）

**Files:**
- Create: `src/skillgap/ingest/extract.py`
- Test: `tests/test_extract.py`

- [ ] **Step 1: 写 tests/test_extract.py（alias 归一 + 证据定位校验）**

```python
from skillgap.ingest.extract import (
    ManualSkillExtractor, alias_map_from_db, load_alias_map, locate_evidence,
    resolve_skill_id,
)
from skillgap.models import SkillAnnotation
from skillgap.taxonomy.seed import seed_taxonomy

JD = "岗位要求：熟悉 RAG 全链路，掌握 LangChain 与 LangGraph 编排，精通 Python。"


def test_alias_map_loads_and_resolves(clean_db):
    seed_taxonomy(clean_db)
    amap = load_alias_map(clean_db)
    # 大小写/别名/规范名均可归一
    assert resolve_skill_id("rag", amap) == resolve_skill_id("RAG", amap)
    assert resolve_skill_id("检索增强生成", amap) == resolve_skill_id("rag", amap)
    assert resolve_skill_id("langchain", amap) is not None
    assert resolve_skill_id("LangChain", amap) == resolve_skill_id("langchain", amap)
    assert resolve_skill_id("完全不存在的技能", amap) is None


def test_locate_evidence_strict():
    assert locate_evidence(JD, "熟悉 RAG 全链路") is True
    assert locate_evidence(JD, "并不存在的证据片段") is False


def test_locate_evidence_tolerates_width_and_case():
    assert locate_evidence("掌握ＲＡＧ技术栈", "掌握RAG技术栈") is True


def test_manual_extractor_passes_through(clean_db):
    anns = [
        SkillAnnotation(raw_name="RAG", importance="must_have",
                        intensity="熟悉", evidence_text="熟悉 RAG 全链路"),
        SkillAnnotation(raw_name="LangGraph", importance="nice_to_have",
                        evidence_text="LangGraph 编排"),
    ]
    result = ManualSkillExtractor(anns).extract(JD)
    assert [a.raw_name for a in result] == ["RAG", "LangGraph"]


def test_manual_extractor_rejects_unlocatable_evidence():
    anns = [SkillAnnotation(raw_name="RAG", importance="must_have",
                            evidence_text="原文没有这句话")]
    try:
        ManualSkillExtractor(anns).extract(JD)
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_alias_map_from_db_helper(clean_db):
    seed_taxonomy(clean_db)
    amap = alias_map_from_db(clean_db)
    assert "langgraph" in amap and "lang graph" in amap
```

- [ ] **Step 2: 写 src/skillgap/ingest/extract.py**

```python
"""S8 抽取接口（SkillExtractor 协议）+ S9 归一（查表，无 LLM）。

LLM 实现属 Phase 3（LLM Gateway）；本阶段 ManualSkillExtractor
承载 Demo Dataset 的人工标注技能（extracted_by='manual'）。
"""
from __future__ import annotations

from typing import Protocol

from skillgap.ingest.normalize import canonicalize_for_hash
from skillgap.models import SkillAnnotation


class SkillExtractor(Protocol):
    def extract(self, jd_text: str) -> list[SkillAnnotation]: ...


class ManualSkillExtractor:
    """S8 手工标注通道：技能来自导入文件的 suggested_skills。"""

    def __init__(self, annotations: list[SkillAnnotation]):
        self._annotations = annotations

    def extract(self, jd_text: str) -> list[SkillAnnotation]:
        # 证据必须可在原文定位（S8 纪律：不可定位即判失败）
        for ann in self._annotations:
            if not locate_evidence(jd_text, ann.evidence_text):
                raise ValueError(
                    f"证据片段无法在 JD 原文定位: {ann.evidence_text!r}")
        return self._annotations


def locate_evidence(jd_text: str, evidence_text: str) -> bool:
    """字符串定位校验（规范化比较，容忍全角/空白/大小写差异）。"""
    return canonicalize_for_hash(evidence_text) in canonicalize_for_hash(jd_text)


def load_alias_map(conn) -> dict[str, int]:
    """alias（含 canonical_name 自身，规范化键）→ skill_id。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT a.alias AS key, a.skill_id AS sid FROM skill_alias a
               UNION SELECT s.canonical_name, s.id FROM skill s""")
        rows = cur.fetchall()
    return {canonicalize_for_hash(r["key"]): r["sid"] for r in rows}


alias_map_from_db = load_alias_map  # 兼容命名


def resolve_skill_id(raw_name: str, alias_map: dict[str, int]) -> int | None:
    return alias_map.get(canonicalize_for_hash(raw_name))


def record_candidates(conn, raw_names: list[str], job_id: int) -> int:
    """S9：无法归一 → new_skill_candidate（不丢弃、不静默入表）。"""
    inserted = 0
    with conn.cursor() as cur:
        for name in raw_names:
            cur.execute(
                """INSERT INTO new_skill_candidate (raw_name, first_seen_job_id)
                   VALUES (%s, %s) ON CONFLICT (raw_name) DO NOTHING""",
                (name, job_id))
            inserted += cur.rowcount
    return inserted
```

- [ ] **Step 3: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_extract.py -v
```
Expected: 6 passed

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/ingest/extract.py tests/test_extract.py
git commit -m "feat(phase2): s8 extractor protocol + manual channel, s9 alias normalization"
```

---

## Task 9: 管道编排 S2-S10 + 批次报告（核心）

**Files:**
- Create: `src/skillgap/ingest/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: 写 src/skillgap/ingest/pipeline.py**

```python
"""S2-S10 管道编排（DATA_PIPELINE §2 逐步落地；每步可独立重跑、失败隔离）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import psycopg

from skillgap.ingest.extract import (
    ManualSkillExtractor, load_alias_map, record_candidates, resolve_skill_id,
)
from skillgap.ingest.normalize import (
    classify_job_category, content_hash, detect_language, determine_market,
    parse_salary_range,
)
from skillgap.ingest.pii import detect_pii, redact
from skillgap.ingest.quality import validate_jd
from skillgap.ingest.sources import get_source
from skillgap.models import BatchReport, RawRecord, RowError

# PII 强制通道（G3：贡献类数据入库前必过 PII；公开 Tier A 源不强制）
PII_REQUIRED_SOURCE_TYPES = {"user_submitted", "csv_import", "dataset_builtin"}


@dataclass
class RecordOutcome:
    status: Literal["inserted", "duplicate", "quarantined", "rejected",
                    "extraction_failed", "error"]
    job_id: int | None = None
    reasons: list[str] = field(default_factory=list)


def _stage_raw(conn, rec: RawRecord) -> int:
    """S2：原始暂存（payload = 脱敏后载荷 for PII 通道，见 DATA_GOVERNANCE §3 双轨）。"""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_jobs (payload, source_fields, status)
               VALUES (%s::jsonb, %s::jsonb, 'pending') RETURNING id""",
            (rec.model_dump_json(), rec.source.model_dump_json()),
        )
        return cur.fetchone()["id"]


def _resolve_company(conn, name: str | None) -> int | None:
    if not name:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO company (name) VALUES (%s)
               ON CONFLICT (name) DO NOTHING RETURNING id""",
            (name.strip(),))
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute("SELECT id FROM company WHERE name = %s", (name.strip(),))
        return cur.fetchone()["id"]


def _dedup_lookup(conn, chash: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM job WHERE content_hash = %s", (chash,))
        row = cur.fetchone()
    return row["id"] if row else None


def process_record(conn, rec: RawRecord, row_index: int = 0) -> tuple[RecordOutcome, dict]:
    """单条记录 S3→S7（+S8/S9 如有标注）→S10。返回 (outcome, 元信息)。"""
    meta: dict = {}

    src = get_source(conn, rec.source.source_name)
    # S3 规范化
    text = rec.raw_text
    language = detect_language(text)
    market = determine_market(language, src["covers_market"])
    ambiguous_market = market is None
    if market is None:
        market = "china" if "china" in src["covers_market"] else "global"
        meta["market_ambiguous"] = True

    # S4/S5 PII（仅贡献类通道强制；Adzuna 双保险：断言 market=global）
    pii_report = None
    if rec.source.source_type in PII_REQUIRED_SOURCE_TYPES:
        findings = detect_pii(text)
        text, pii_report = redact(text, findings)
    if rec.source.source_type == "public_api" and market != "global":
        return RecordOutcome("rejected", reasons=["market_guard_violation"]), meta

    # S6 去重（content_hash 在脱敏后文本上计算）
    chash = content_hash(text)
    existing = _dedup_lookup(conn, chash)
    if existing is not None:
        return RecordOutcome("duplicate", job_id=existing), meta

    # S7 质检
    verdict = validate_jd(rec.title, text)
    if verdict.verdict == "reject":
        _mark_raw(conn, rec, "rejected", ",".join(verdict.reasons))
        return RecordOutcome("rejected", reasons=verdict.reasons), meta
    if verdict.verdict == "quarantine":
        _mark_raw(conn, rec, "quarantined", ",".join(verdict.reasons))
        return RecordOutcome("quarantined", reasons=verdict.reasons), meta

    # S8 抽取（手工标注通道；LLM Phase 3）
    annotations = []
    extraction_error = None
    if rec.suggested_skills:
        try:
            annotations = ManualSkillExtractor(rec.suggested_skills).extract(text)
        except ValueError as e:
            extraction_error = str(e)

    # S10 入库（事务：job + job_skill）
    job_category = rec.job_category or classify_job_category(rec.title, text)
    salary_min, salary_max = rec.salary_min, rec.salary_max
    if salary_min is None and text:
        salary_min, salary_max = parse_salary_range(text)

    alias_map = load_alias_map(conn)
    parsed_metadata = {"market_ambiguous": ambiguous_market}
    if pii_report:
        parsed_metadata["pii_redaction"] = pii_report
    if rec.source.source_type in ("user_submitted",) and not annotations:
        parsed_metadata["extraction_status"] = "pending"  # Phase 3 LLM 回填

    status = "extraction_failed" if extraction_error else "active"
    with conn.transaction():
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO job (title, job_category, company_id, city, country,
                   region, market, language, salary_min, salary_max,
                   salary_currency, raw_text, status, source_id, source_type,
                   source_url, collected_at, submitted_at, content_hash,
                   consent_status, data_quality, soft_requirements,
                   parsed_metadata)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id""",
                (rec.title.strip(), job_category,
                 _resolve_company(conn, rec.company_name), rec.city, rec.country,
                 rec.region, market, language or "zh", salary_min, salary_max,
                 rec.salary_currency, text, status, src["id"],
                 rec.source.source_type, rec.source.source_url,
                 rec.source.collected_at, rec.source.submitted_at, chash,
                 rec.source.consent_status, rec.source.data_quality,
                 _jsonb(rec.soft_requirements), _jsonb(parsed_metadata)),
            )
            job_id = cur.fetchone()["id"]

            if extraction_error is None and annotations:
                unresolved: list[str] = []
                for ann in annotations:
                    skill_id = resolve_skill_id(ann.raw_name, alias_map)
                    if skill_id is None:
                        unresolved.append(ann.raw_name)
                        continue
                    cur.execute(
                        """INSERT INTO job_skill (job_id, skill_id, importance,
                           intensity, evidence_text, extracted_by)
                           VALUES (%s,%s,%s,%s,%s,'manual')
                           ON CONFLICT (job_id, skill_id) DO NOTHING""",
                        (job_id, skill_id, ann.importance, ann.intensity,
                         ann.evidence_text))
                if unresolved:
                    record_candidates(conn, unresolved, job_id)

    _mark_raw(conn, rec, "done", None)
    if extraction_error:
        return (RecordOutcome("extraction_failed", job_id=job_id,
                              reasons=[extraction_error]), meta)
    return RecordOutcome("inserted", job_id=job_id), meta


def _jsonb(value):
    import json

    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _mark_raw(conn, rec: RawRecord, status: str, error: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_jobs (payload, source_fields, status, error, processed_at)
               VALUES (%s::jsonb, %s::jsonb, %s, %s, now())""",
            (rec.model_dump_json(), rec.source.model_dump_json(), status, error))
    conn.commit()


def run_batch(conn, records: list[RawRecord]) -> BatchReport:
    """批次入口：逐条处理（行级失败不中断整批），产出导入报告并入 ingest_batch。"""
    if not records:
        return BatchReport(source_name="(empty)")
    report = BatchReport(source_name=records[0].source.source_name)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ingest_batch (source_name, source_type, total)
               VALUES (%s, %s, %s) RETURNING id""",
            (report.source_name, records[0].source.source_type, len(records)))
        batch_id = cur.fetchone()["id"]
    conn.commit()

    for i, rec in enumerate(records):
        report.total += 1
        try:
            outcome, _meta = process_record(conn, rec, row_index=i)
        except Exception as e:  # 行级错误：记录不中断
            report.errors.append(RowError(row=i, stage="pipeline", message=str(e)))
            conn.rollback()
            continue
        if outcome.status == "inserted":
            report.inserted += 1
        elif outcome.status == "duplicate":
            report.duplicates += 1
        elif outcome.status == "quarantined":
            report.quarantined += 1
        elif outcome.status == "rejected":
            report.rejected += 1
        elif outcome.status == "extraction_failed":
            report.extraction_failed += 1

    with conn.cursor() as cur:
        cur.execute(
            """UPDATE ingest_batch SET inserted=%s, duplicates=%s, quarantined=%s,
               rejected=%s, extraction_failed=%s, finished_at=now(), errors=%s
               WHERE id=%s""",
            (report.inserted, report.duplicates, report.quarantined,
             report.rejected, report.extraction_failed, _jsonb(
                 [e.model_dump() for e in report.errors]), batch_id))
    conn.commit()
    return report
```

- [ ] **Step 2: 写 tests/test_pipeline.py（S2-S10 端到端 + 幂等重跑 + B1 口径）**

```python
from datetime import datetime, timezone

from skillgap.ingest.pipeline import process_record, run_batch
from skillgap.models import RawRecord, SkillAnnotation, SourceFields

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)

GOOD_JD = ("岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排，"
           "优化 Prompt 与线上推理服务。任职要求：熟悉 LangChain、LangGraph，"
           "精通 Python，了解 Docker 部署。") * 2

SKILLS = [
    SkillAnnotation(raw_name="RAG", importance="must_have", intensity="熟悉",
                    evidence_text="搭建 RAG 检索链路"),
    SkillAnnotation(raw_name="LangChain", importance="must_have", intensity="熟悉",
                    evidence_text="熟悉 LangChain"),
    SkillAnnotation(raw_name="Python", importance="must_have", intensity="精通",
                    evidence_text="精通 Python"),
]


def _rec(**source_over) -> RawRecord:
    src = dict(source_type="dataset_builtin", source_name="demo_dataset",
               collected_at=NOW, source_url=None)
    src.update({k: v for k, v in dict() .items()})
    return RawRecord(
        title="AI 应用开发工程师", raw_text=GOOD_JD,
        suggested_skills=[
            SkillAnnotation(raw_name="RAG", importance="must_have",
                            intensity="熟悉", evidence_text="搭建 RAG 检索链路"),
            SkillAnnotation(raw_name="Python", importance="must_have",
                            intensity="精通", evidence_text="精通 Python"),
        ],
        source=SourceFields(**src),
    )


def test_insert_active_job_with_skills(clean_db):
    outcome, meta = process_record(clean_db, _rec())
    assert outcome.status == "inserted"
    assert meta.get("market_ambiguous") is not True
    with clean_db.cursor() as cur:
        cur.execute("SELECT * FROM job WHERE id = %s", (outcome.job_id,))
        job = cur.fetchone()
        cur.execute("SELECT count(*) AS c FROM job_skill WHERE job_id = %s",
                    (outcome.job_id,))
        n = cur.fetchone()["c"]
    assert job["market"] == "china"
    assert job["language"] == "zh"
    assert job["status"] == "active"
    assert job["consent_status"] == "none"
    assert n == 2


def test_dedup_same_content_returns_existing(clean_db):
    a, _ = process_record(clean_db, _rec())
    b, _ = process_record(clean_db, _rec())
    assert b.status == "duplicate" and b.job_id == a.job_id
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job")
        assert cur.fetchone()["c"] == 1


def test_quarantine_short_jd_stored_in_raw_jobs(clean_db):
    rec = _rec()
    rec.raw_text = "太短"
    outcome, _ = process_record(clean_db, rec)
    assert outcome.status == "quarantined"
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job")
        assert cur.fetchone()["c"] == 0          # 未入库
        cur.execute("SELECT status, error FROM raw_jobs")
        row = cur.fetchone()
    assert row["status"] == "quarantined"
    assert "length" in row["error"]


def test_unresolvable_skill_goes_to_candidates(clean_db):
    rec = _rec()
    rec.suggested_skills = [
        SkillAnnotation(raw_name="某未知新框架", importance="nice_to_have",
                        evidence_text="负责大模型应用开发")]
    outcome, _ = process_record(clean_db, rec)
    assert outcome.status == "inserted"
    with clean_db.cursor() as cur:
        cur.execute("SELECT raw_name, status FROM new_skill_candidate")
        row = cur.fetchone()
    assert row["raw_name"] == "某未知新框架" and row["status"] == "pending"


def test_evidence_not_locatable_marks_extraction_failed(clean_db):
    rec = _rec()
    rec.suggested_skills = [
        SkillAnnotation(raw_name="RAG", importance="must_have",
                        evidence_text="原文不存在的片段")]
    outcome, _ = process_record(clean_db, rec)
    assert outcome.status == "extraction_failed"
    with clean_db.cursor() as cur:
        cur.execute("SELECT status FROM job WHERE id = %s", (outcome.job_id,))
        assert cur.fetchone()["status"] == "extraction_failed"  # 不进统计


def test_user_submitted_pii_redacted_before_insert(clean_db):
    rec = _rec()
    rec.source.source_type = "user_submitted"
    rec.source.source_name = "user_contribution"
    rec.source.consent_status = "market_analysis"
    rec.raw_text = "联系张三 13812345678。" + GOOD_JD
    outcome, _ = process_record(clean_db, rec)
    assert outcome.status == "inserted"
    with clean_db.cursor() as cur:
        cur.execute("SELECT raw_text, parsed_metadata FROM job WHERE id=%s",
                    (outcome.job_id,))
        row = cur.fetchone()
    assert "13812345678" not in row["raw_text"]
    assert "[PHONE_REDACTED]" in row["raw_text"]
    assert row["parsed_metadata"]["pii_redaction"]["hits"]["phone"] == 1


def test_run_batch_report_counts(clean_db):
    records = [_rec(), _rec()]                    # 第二条重复
    bad = _rec(); bad.raw_text = "太短"           # 一条隔离
    records.append(bad)
    report = run_batch(clean_db, records)
    assert report.total == 3
    assert report.inserted == 1
    assert report.duplicates == 1
    assert report.quarantined == 1
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT total, inserted, duplicates, quarantined FROM ingest_batch")
        row = cur.fetchone()
    assert (row["total"], row["inserted"], row["duplicates"],
            row["quarantined"]) == (3, 1, 1, 1)


def test_batch_idempotent_rerun(clean_db):
    run_batch(clean_db, [_rec()])
    report = run_batch(clean_db, [_rec()])
    assert report.duplicates == 1 and report.inserted == 0
```

注意：`test_user_submitted_pii_redacted_before_insert` 中 phone 命中位置在句首附近，需确认 contact 规则不误吞 "联系张三 138..."（contact 匹配 "联系张三"，phone 匹配号码，二者不重叠，均替换）。若断言失败，先检查规则顺序。

- [ ] **Step 3: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_pipeline.py -v
```
Expected: 8 passed

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/ingest/pipeline.py tests/test_pipeline.py
git commit -m "feat(phase2): s2-s10 pipeline orchestration with batch report and ingest_batch history"
```

---

## Task 10: CSV/JSON 导入器（S1 批量导入流）

**Files:**
- Create: `src/skillgap/ingest/importer.py`
- Create: `data/collect_template.csv`
- Test: `tests/test_importer.py`

- [ ] **Step 1: 写 tests/test_importer.py**

```python
import json
from datetime import datetime, timezone

import pytest

from skillgap.ingest.importer import REQUIRED_COLUMNS, parse_file

CSV_CONTENT = """title,company,city,country,region,salary_min,salary_max,salary_currency,job_category,raw_text,soft_requirements,skills,source_type,source_name,source_url,collected_at,submitted_at,consent_status,data_quality
AI 应用开发工程师,某科技,北京,中国,华北,,15000,25000,CNY,,{jd} ,,; ;"[{{""raw_name"":""RAG"",""importance"":""must_have"",""intensity"":""熟悉"",""evidence_text"":""搭建 RAG 检索链路""}}]",public_job_page,company_career_page,https://example.com/j/1,2026-08-31,,,auto_passed
Agent 工程师,,,,,,,CNY,,{jd} ,"[{{""raw_name"":""LangGraph"",""importance"":""must_have"",""evidence_text"":""Agent 编排""}}]",public_job_page,company_career_page,https://example.com/j/2,2026-08-31,,,auto_passed
""".replace("{jd} ", "岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。")


def _write(tmp_path, content, name, encoding="utf-8"):
    p = tmp_path / name
    p.write_text(content, encoding=encoding)
    return str(p)


def test_parse_csv_ok(tmp_path):
    path = _write(tmp_path, CSV_CONTENT, "jobs.csv")
    records = parse_file(path)
    assert len(records) == 2
    assert records[0].source.source_type == "public_job_page"
    assert records[0].source.source_url == "https://example.com/j/1"
    assert records[0].suggested_skills[0].raw_name == "RAG"
    assert records[0].salary_max == 25000
    assert records[1].job_category == "" or records[1].job_category is None


def test_parse_json_ok(tmp_path):
    data = [{
        "title": "AI 应用开发工程师",
        "raw_text": "岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。",
        "city": "北京",
        "skills": [{"raw_name": "RAG", "importance": "must_have",
                    "evidence_text": "搭建 RAG 检索链路"}],
        "source_type": "dataset_builtin", "source_name": "demo_dataset",
        "collected_at": "2026-08-31T00:00:00Z",
    }]
    path = _write(tmp_path, json.dumps(data, ensure_ascii=False), "jobs.json")
    records = parse_file(path)
    assert len(records) == 1
    assert records[0].source.source_name == "demo_dataset"


def test_missing_required_columns_rejected(tmp_path):
    path = _write(tmp_path, "title,raw_text\nx,y", "bad.csv")
    with pytest.raises(ValueError) as e:
        parse_file(path)
    assert "missing" in str(e.value).lower()


def test_row_level_error_does_not_abort(tmp_path):
    rows = [
        {"title": "AI 工程师",
         "raw_text": "岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。",
         "source_type": "dataset_builtin", "source_name": "demo_dataset",
         "collected_at": "2026-08-31T00:00:00Z"},
        {"title": "坏行", "raw_text": "缺 source",
         "source_type": "dataset_builtin", "source_name": "demo_dataset"},
    ]
    path = _write(tmp_path, json.dumps(rows), "mixed.json")
    with pytest.warns(UserWarning):
        records = parse_file(path)
    assert len(records) == 1


def test_utf8_bom_tolerated(tmp_path):
    path = _write(tmp_path, "\ufeff" + CSV_CONTENT, "bom.csv")
    assert len(parse_file(path)) == 2
```

- [ ] **Step 2: 写 src/skillgap/ingest/importer.py**

```python
"""S1 CSV/JSON 批量导入器（Tier C；列规格 = DATA_MODEL §7）。"""
from __future__ import annotations

import csv
import json
import warnings
from pathlib import Path

from skillgap.models import RawRecord, SkillAnnotation, SourceFields

REQUIRED_COLUMNS = {
    "title", "raw_text", "source_type", "source_name", "collected_at",
}


def parse_file(path: str | Path) -> list[RawRecord]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        if rows and not REQUIRED_COLUMNS.issubset(rows[0].keys()):
            missing = REQUIRED_COLUMNS - set(rows[0].keys())
            raise ValueError(f"CSV 缺少必需列: {sorted(missing)}（整批拒绝）")
        return _from_rows(rows, p)
    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("JSON 顶层必须是数组（整批拒绝）")
        return _from_rows(data, p)
    raise ValueError(f"不支持的文件类型: {p.suffix}（仅 CSV/JSON）")


def _from_rows(rows: list, path: Path) -> list[RawRecord]:
    records: list[RawRecord] = []
    for i, row in enumerate(rows, start=2 if isinstance(rows[0], dict) and "raw_text" in rows[0] and hasattr(rows[0], "keys") else 1):
        try:
            records.append(_to_record(row))
        except Exception as e:
            warnings.warn(f"{path.name} 第 {i} 行解析失败，已跳过: {e}", UserWarning)
    return records


def _to_record(row: dict) -> RawRecord:
    skills_raw = row.get("skills") or "[]"
    if isinstance(skills_raw, str):
        skills_raw = json.loads(skills_raw)
    source = SourceFields(
        source_type=row["source_type"],
        source_name=row["source_name"],
        source_url=row.get("source_url") or None,
        collected_at=row["collected_at"],
        submitted_at=row.get("submitted_at") or None,
        license_or_usage_note=row.get("license_or_usage_note", ""),
        consent_status=row.get("consent_status") or "none",
        data_quality=row.get("data_quality") or "auto_passed",
    )
    soft = row.get("soft_requirements") or None
    if isinstance(soft, str):
        soft = json.loads(soft)
    job_category = (row.get("job_category") or "").strip() or None
    return RawRecord(
        title=row["title"],
        raw_text=row["raw_text"],
        company_name=row.get("company") or None,
        city=row.get("city") or None,
        country=row.get("country") or None,
        region=row.get("region") or None,
        salary_min=_int_or_none(row.get("salary_min")),
        salary_max=_int_or_none(row.get("salary_max")),
        salary_currency=row.get("salary_currency") or None,
        job_category=job_category,
        soft_requirements=soft,
        suggested_skills=[SkillAnnotation(**s) for s in skills_raw],
        source=source,
    )


def _int_or_none(v):
    if v in (None, ""):
        return None
    return int(float(v))
```

注意 `_from_rows` 的行号起点判断写得过于复杂，执行时简化为：CSV 用 `enumerate(rows, start=2)`、JSON 用 `enumerate(rows, start=1)`（在两个分支里分别调用），行为一致且可读。**实现以简化版为准。**

- [ ] **Step 3: 写 data/collect_template.csv（Demo Dataset 收集模板 + 2 条示例行）**

```csv
title,company,city,country,region,salary_min,salary_max,salary_currency,job_category,raw_text,soft_requirements,skills,source_type,source_name,source_url,collected_at,submitted_at,consent_status,data_quality
AI 应用开发工程师,示例公司,北京,中国,华北,15000,25000,CNY,ai_application_dev,"岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排，优化 Prompt 工程。任职要求：熟悉 LangChain、LangGraph，精通 Python，了解 Docker 部署。","[{""type"":""experience"",""value"":""1-3年"",""evidence_text"":""1-3年大模型应用开发经验""}]","[{""raw_name"":""RAG"",""importance"":""must_have"",""intensity"":""熟悉"",""evidence_text"":""搭建 RAG 检索链路""},{""raw_name"":""Python"",""importance"":""must_have"",""intensity"":""精通"",""evidence_text"":""精通 Python""},{""raw_name"":""Docker"",""importance"":""nice_to_have"",""intensity"":""了解"",""evidence_text"":""了解 Docker 部署""}]",public_job_page,company_career_page,https://hr.example.com/job/1001,2026-08-31,,none,verified
LLM 平台工程师,示例公司2,上海,中国,华东,,40000,60000,CNY,ai_platform,"岗位职责：负责推理服务与模型部署平台建设，使用 vLLM 提升吞吐，维护 Kubernetes 集群。","[{""type"":""education"",""value"":""本科及以上""}]","[{""raw_name"":""vLLM"",""importance"":""must_have"",""intensity"":""熟悉"",""evidence_text"":""使用 vLLM 提升吞吐""},{""raw_name"":""Kubernetes"",""importance"":""must_have"",""intensity"":""熟悉"",""evidence_text"":""维护 Kubernetes 集群""}]",public_job_page,company_career_page,https://hr.example.com/job/1002,2026-08-31,,none,verified
```

- [ ] **Step 4: 运行测试 + 模板导入冒烟（验证模板本身合法）**

```powershell
.\.venv\Scripts\pytest tests/test_importer.py -v
.\.venv\Scripts\python -c "from skillgap.ingest.importer import parse_file; rs = parse_file('data/collect_template.csv'); print(len(rs), rs[0].title)"
```
Expected: 测试全过；`2 AI 应用开发工程师`

- [ ] **Step 5: Commit**

```powershell
git add src/skillgap/ingest/importer.py data/collect_template.csv tests/test_importer.py
git commit -m "feat(phase2): csv/json importer + demo dataset collection template"
```

---

## Task 11: Adzuna 连接器（S1 海外 Ingest 流）

**Files:**
- Create: `src/skillgap/ingest/adzuna.py`
- Test: `tests/test_adzuna.py`

- [ ] **Step 1: 写 tests/test_adzuna.py（MockTransport，不发真实请求）**

```python
import httpx
import pytest

from skillgap.ingest.adzuna import (
    ADZUNA_ATTRIBUTION, AdzunaClient, check_daily_quota, fetch_adzuna,
)
from skillgap.ingest.pipeline import run_batch  # noqa: F401 (确保模块可用)

PAGE = {
    "count": 60, "mean": 0.0, "results": [
        {
            "id": "a1b2c3", "title": "AI Engineer",
            "description": "We need an LLM engineer with RAG experience and "
                           "strong Python skills. " * 5,
            "company": {"display_name": "Acme Ltd"},
            "location": {"display_name": "London, Greater London"},
            "salary_min": 45000, "salary_max": 65000,
            "redirect_url": "https://example.com/adzuna/a1b2c3",
        },
    ],
}


def _client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return AdzunaClient(app_id="id", app_key="key", http=http,
                        base_url="https://adzuna.test/v1/api/jobs")


def test_fetch_page_maps_to_raw_records():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(200, json=PAGE)

    client = _client(handler)
    records = client.fetch_page(country="gb", query="LLM", page=1)
    assert len(records) == 1
    rec = records[0]
    assert rec.title == "AI Engineer"
    assert rec.company_name == "Acme Ltd"
    assert rec.city == "London, Greater London"
    assert rec.source.source_type == "public_api"
    assert rec.source.source_name == "adzuna"
    assert rec.source.source_url == "https://example.com/adzuna/a1b2c3"
    assert rec.salary_max == 65000
    assert "app_id=id" in str(calls[0])


def test_retry_on_500_then_success():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=PAGE)

    client = _client(handler)
    records = client.fetch_page("gb", "LLM", 1)
    assert attempts["n"] == 2 and len(records) == 1


def test_upstream_error_after_3_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _client(handler)
    with pytest.raises(RuntimeError, match="Adzuna"):
        client.fetch_page("gb", "LLM", 1)


def test_quota_guard_blocks_over_limit(clean_db):
    import psycopg
    with clean_db.cursor() as cur:
        for _ in range(250):
            cur.execute(
                "INSERT INTO ingest_request_log (source_name) VALUES ('adzuna')")
    clean_db.commit()
    with pytest.raises(RuntimeError, match="额度"):
        check_daily_quota(clean_db, limit=250)


def test_fetch_adzuna_pipeline_integration(clean_db):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=PAGE)

    client = _client(handler)
    report = fetch_adzuna(clean_db, country="gb", query="LLM",
                          max_results=10, client=client)
    assert report.total >= 1
    assert report.inserted >= 1
    assert report.attribution == ADZUNA_ATTRIBUTION
    with clean_db.cursor() as cur:
        cur.execute("SELECT market, language, source_type FROM job")
        row = cur.fetchone()
        cur.execute("SELECT count(*) AS c FROM ingest_checkpoint "
                    "WHERE source_name='adzuna'")
        ckpt = cur.fetchone()["c"]
    assert row["market"] == "global"           # 无污染（验收红线）
    assert row["source_type"] == "public_api"
    assert ckpt == 1                            # checkpoint 已记录
```

- [ ] **Step 2: 写 src/skillgap/ingest/adzuna.py**

```python
"""S1 Adzuna 连接器（Tier A，Global 专用）。

合规（DATA_GOVERNANCE §6）：
- 仓库只分发连接器代码，不分发数据（用户自行运行 ingest）；
- 遵守免费层限额（本地额度守卫前置）；
- 展示层带 "Jobs by Adzuna" 归属。
失败处理（DATA_PIPELINE S1）：429/5xx 指数退避重试 ≤3，仍失败记录 checkpoint 次日续拉。
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx
import psycopg

from skillgap.ingest.pipeline import run_batch
from skillgap.models import BatchReport, RawRecord, SourceFields

ADZUNA_ATTRIBUTION = "Jobs by Adzuna"
RESULTS_PER_PAGE = 50
MAX_RETRIES = 3


class AdzunaClient:
    def __init__(self, app_id: str, app_key: str,
                 http: httpx.Client | None = None,
                 base_url: str = "https://api.adzuna.com/v1/api/jobs"):
        self.app_id = app_id
        self.app_key = app_key
        self.base_url = base_url.rstrip("/")
        self.http = http or httpx.Client(timeout=10.0)

    def fetch_page(self, country: str, query: str, page: int) -> list[RawRecord]:
        params = {
            "app_id": self.app_id, "app_key": self.app_key,
            "results_per_page": RESULTS_PER_PAGE, "what": query, "page": page,
        }
        url = f"{self.base_url}/{country}/search/{page}"
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self.http.get(url, params=params)
                if resp.status_code in (429, 500, 502, 503, 504):
                    retry_after = resp.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2 ** attempt
                    time.sleep(min(delay, 30))
                    last_error = RuntimeError(
                        f"Adzuna 返回 {resp.status_code}")
                    continue
                resp.raise_for_status()
                return self._map_results(resp.json(), country)
            except (httpx.HTTPError, RuntimeError) as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"Adzuna 重试 {MAX_RETRIES} 次后仍失败: {last_error}")

    def _map_results(self, payload: dict, country: str) -> list[RawRecord]:
        now = datetime.now(timezone.utc)
        records = []
        for item in payload.get("results", []):
            company = (item.get("company") or {}).get("display_name")
            location = (item.get("location") or {}).get("display_name")
            records.append(RawRecord(
                title=item.get("title") or "",
                raw_text=item.get("description") or "",
                company_name=company,
                city=location,
                country=country.upper(),
                salary_min=item.get("salary_min"),
                salary_max=item.get("salary_max"),
                salary_currency=None,
                source=SourceFields(
                    source_type="public_api",
                    source_name="adzuna",
                    source_url=item.get("redirect_url"),
                    collected_at=now,
                    license_or_usage_note="Adzuna ToS: attribution + no redistribution",
                ),
            ))
        return records


def check_daily_quota(conn: psycopg.Connection, limit: int = 250) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS c FROM ingest_request_log "
            "WHERE source_name='adzuna' AND requested_at::date = CURRENT_DATE")
        used = cur.fetchone()["c"]
    if used >= limit:
        raise RuntimeError(
            f"本地额度守卫：Adzuna 今日已用 {used}/{limit} 请求（DATA_GOVERNANCE §6）")


def _log_request(conn, status_code: int | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO ingest_request_log (source_name, status_code) "
            "VALUES ('adzuna', %s)", (status_code,))
    conn.commit()


def _save_checkpoint(conn, country: str, query: str, page: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ingest_checkpoint (source_name, scope_key, last_page)
               VALUES ('adzuna', %s, %s)
               ON CONFLICT (source_name, scope_key)
               DO UPDATE SET last_page = EXCLUDED.last_page, updated_at = now()""",
            (f"country:{country}|query:{query}", page))
    conn.commit()


def fetch_adzuna(conn: psycopg.Connection, country: str, query: str,
                 max_results: int = 500,
                 client: AdzunaClient | None = None) -> BatchReport:
    """拉取 → S3-S10 管道入库。market=global 由 data_source + 服务层双保险。"""
    from skillgap.config import settings

    check_daily_quota(conn, limit=settings.adzuna_daily_quota)
    client = client or AdzunaClient(settings.adzuna_app_id,
                                    settings.adzuna_app_key,
                                    base_url=settings.adzuna_base_url)
    pages = (max_results + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    all_records: list[RawRecord] = []
    for page in range(1, pages + 1):
        _log_request(conn, 200)
        records = client.fetch_page(country, query, page)
        all_records.extend(records)
        _save_checkpoint(conn, country, query, page)
        if len(records) < RESULTS_PER_PAGE:
            break
    report = run_batch(conn, all_records)
    report.attribution = ADZUNA_ATTRIBUTION
    return report
```

- [ ] **Step 3: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_adzuna.py -v
```
Expected: 5 passed

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/ingest/adzuna.py tests/test_adzuna.py
git commit -m "feat(phase2): adzuna connector with retry, quota guard, checkpoint"
```

---

## Task 12: 用户贡献通道 + deletion_code（S1 在线流核心）

**Files:**
- Create: `src/skillgap/ingest/contribute.py`
- Test: `tests/test_contribute.py`

- [ ] **Step 1: 写 tests/test_contribute.py**

```python
import pytest

from skillgap.ingest.contribute import (
    ContributeResult, contribute_jd, delete_contribution,
)

JD = ("岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。"
      "任职要求：熟悉 LangChain，精通 Python。") * 2


def test_contribute_requires_consent(clean_db):
    with pytest.raises(ValueError, match="consent"):
        contribute_jd(clean_db, jd_text=JD, consent=False, title="AI 工程师")


def test_contribute_success_with_redaction_and_deletion_code(clean_db):
    text = "联系张三 13812345678。" + JD
    result = contribute_jd(clean_db, jd_text=text, consent=True,
                           title="AI 应用开发工程师", source_hint="boss")
    assert result.deduplicated is False
    assert result.job_id > 0
    assert len(result.deletion_code) >= 8
    assert result.pii_redaction["hits"]["phone"] == 1
    with clean_db.cursor() as cur:
        cur.execute("SELECT raw_text, consent_status, market, source_type,"
                    " submitted_at, status FROM job WHERE id=%s", (result.job_id,))
        row = cur.fetchone()
    assert "13812345678" not in row["raw_text"]
    assert row["consent_status"] == "market_analysis"
    assert row["source_type"] == "user_submitted"
    assert row["market"] == "china"
    assert row["submitted_at"] is not None
    assert row["status"] == "active"


def test_duplicate_contribution_returns_existing(clean_db):
    a = contribute_jd(clean_db, JD, True, "AI 工程师")
    b = contribute_jd(clean_db, JD, True, "AI 工程师")
    assert b.deduplicated is True
    assert b.job_id == a.job_id
    assert b.deletion_code is None      # 重复提交不发新 code


def test_delete_by_code_roundtrip(clean_db):
    r = contribute_jd(clean_db, JD, True, "AI 工程师")
    assert delete_contribution(clean_db, r.deletion_code) is True
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job WHERE id=%s", (r.job_id,))
        assert cur.fetchone()["c"] == 0
    # 错误 code 返回 False（不区分不存在/已删——防探测，API §2.14）
    assert delete_contribution(clean_db, r.deletion_code) is False


def test_quarantined_contribution_raises(clean_db):
    with pytest.raises(RuntimeError, match="quarantine"):
        contribute_jd(clean_db, jd_text="太短的JD", consent=True, title="x工程师")
```

- [ ] **Step 2: 写 src/skillgap/ingest/contribute.py**

```python
"""S1 用户贡献通道（Tier B，中国市场主通道；DATA_GOVERNANCE §3）。

opt-in（默认不贡献）→ PII 检测/脱敏 → 去重 → 质检 → 入库（consent=market_analysis）。
deletion_code 明文仅一次性返回，库中只存哈希（防探测）。
"""
from __future__ import annotations

import hashlib
import secrets
import string
from datetime import datetime, timezone

import psycopg

from skillgap.ingest.normalize import content_hash
from skillgap.ingest.pii import detect_pii, redact
from skillgap.ingest.pipeline import process_record
from skillgap.ingest.quality import MIN_LEN, MAX_LEN, validate_jd
from skillgap.models import RawRecord, SourceFields

_ALPHABET = string.ascii_uppercase + string.digits


class QuarantinedContribution(RuntimeError):
    pass


class ConsentRequired(ValueError):
    pass


class ContributeResult:
    def __init__(self, job_id: int | None, deduplicated: bool,
                 pii_redaction: dict | None, deletion_code: str | None):
        self.job_id = job_id
        self.deduplicated = deduplicated
        self.pii_redaction = pii_redaction
        self.deletion_code = deletion_code


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def contribute_jd(conn: psycopg.Connection, jd_text: str, consent: bool,
                  title: str, source_hint: str = "other") -> ContributeResult:
    """source_hint 仅作来源统计标签（API §2.2）；系统不向任何平台发请求。"""
    if not consent:
        raise ConsentRequired("consent=false：未经同意不入库（B1 口径）")
    if not (MIN_LEN <= len(jd_text.strip()) <= MAX_LEN):
        raise ValueError(f"JD 长度须在 {MIN_LEN}-{MAX_LEN} 字符（VALIDATION_ERROR）")

    # S4/S5（G3 门禁：贡献通道强制）
    findings = detect_pii(jd_text)
    redacted, report = redact(jd_text, findings)

    # S6 预检去重（process_record 内有 DB 唯一约束兜底）
    chash = content_hash(redacted)
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM job WHERE content_hash = %s", (chash,))
        existing = cur.fetchone()
    if existing:
        return ContributeResult(existing["id"], True, report, None)

    # S7 质检（隔离 → 抛错并留 raw 队列）
    verdict = validate_jd(title, redacted)
    if verdict.verdict != "pass":
        rec = _to_record(redacted, title, source_hint, chash)
        _stage_quarantined(conn, rec, verdict.reasons)
        raise QuarantinedContribution(
            f"QUARANTINED（原因: {verdict.reasons}）——人工复核队列")

    rec = _to_record(redacted, title, source_hint, chash)
    outcome, _meta = process_record(conn, rec)
    if outcome.status in ("quarantined", "rejected"):
        raise QuarantinedContribution(f"QUARANTINED（{outcome.reasons}）")
    if outcome.status == "error" or outcome.job_id is None:
        raise RuntimeError(f"贡献入库失败: {outcome.status} {outcome.reasons}")

    # deletion_code：明文一次性返回
    code = "-".join("".join(secrets.choice(_ALPHABET) for _ in range(4))
                    for _ in range(2))
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO deletion_code (job_id, code_hash) VALUES (%s, %s)",
            (outcome.job_id, _hash_code(code)))
    conn.commit()
    return ContributeResult(outcome.job_id, False, report, code)


def _to_record(redacted_text: str, title: str, source_hint: str,
               chash: str) -> RawRecord:
    src = SourceFields(
        source_type="user_submitted",
        source_name="user_contribution",
        collected_at=datetime.now(timezone.utc),
        submitted_at=datetime.now(timezone.utc),
        content_hash=chash,
        license_or_usage_note="user opt-in anonymous contribution",
        consent_status="market_analysis",
        data_quality="auto_passed",
    )
    src.model_extra = None
    return RawRecord(
        title=title,
        raw_text=redacted_text,
        parsed_source_hint=source_hint,  # 见下方说明
        source=src,
    )


def _stage_quarantined(conn, rec: RawRecord, reasons: list[str]) -> None:
    import json

    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO raw_jobs (payload, source_fields, status, error)
               VALUES (%s::jsonb, %s::jsonb, 'quarantined', %s)""",
            (rec.model_dump_json(), rec.source.model_dump_json(),
             json.dumps(reasons)))
    conn.commit()


def delete_contribution(conn: psycopg.Connection, code: str) -> bool:
    """凭 code 删除贡献（级联 job_skill/deletion_code）；错误一律 False（防探测）。"""
    with conn.cursor() as cur:
        cur.execute(
            """DELETE FROM job WHERE id IN (
                 SELECT job_id FROM deletion_code WHERE code_hash = %s)
               RETURNING id""",
            (_hash_code(code),))
        deleted = cur.fetchone()
    conn.commit()
    return deleted is not None
```

**实现说明（执行时落实）：** `_to_record` 中 `parsed_source_hint` 不是 RawRecord 字段——source_hint 写入 `parsed_metadata` 更合理。执行时改为：`RawRecord(title=title, raw_text=redacted_text, source=src)`，并在 contribute_jd 里 process_record 之后执行：

```python
with conn.cursor() as cur:
    cur.execute(
        "UPDATE job SET parsed_metadata = coalesce(parsed_metadata, '{}'::jsonb)"
        " || jsonb_build_object('source_hint', %s) WHERE id = %s",
        (source_hint, outcome.job_id))
conn.commit()
```
删除 `parsed_source_hint` 行与 `model_extra` 行。

- [ ] **Step 3: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_contribute.py -v
```
Expected: 5 passed

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/ingest/contribute.py tests/test_contribute.py
git commit -m "feat(phase2): opt-in contribution channel with pii, dedup, deletion code"
```

---

## Task 13: E5 数据质量指标 + 报告

**Files:**
- Create: `src/skillgap/quality_metrics.py`
- Test: `tests/test_quality_metrics.py`（并入 test_pipeline.py 同级目录）

- [ ] **Step 1: 写 tests/test_quality_metrics.py**

```python
from datetime import datetime, timezone

from skillgap.ingest.pipeline import run_batch
from skillgap.quality_metrics import batch_metrics, full_scan
from tests.test_pipeline import _rec, _rec as make_rec  # 复用构造器

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def test_batch_metrics_rates(clean_db):
    records = [make_rec(), make_rec()]
    bad = make_rec(); bad.raw_text = "太短"
    records.append(bad)
    report = run_batch(clean_db, records)
    m = batch_metrics(report)
    assert m["duplicate_rate"] == round(1 / 3, 4)
    assert m["invalid_jd_rate"] == round(1 / 3, 4)
    assert m["skill_extraction_error_rate"] == 0.0


def test_full_scan_missing_field_rate_zero(clean_db):
    run_batch(clean_db, [make_rec()])
    scan = full_scan(clean_db)
    assert scan["missing_field_rate"] == 0.0
    assert scan["job_count"] == 1


def test_full_scan_pii_aggregation(clean_db):
    rec = make_rec()
    rec.source.source_type = "user_submitted"
    rec.source.source_name = "user_contribution"
    rec.source.consent_status = "market_analysis"
    rec.raw_text = "联系张三 13812345678。" + rec.raw_text
    run_batch(clean_db, [rec])
    scan = full_scan(clean_db)
    assert scan["pii_scan_count"] >= 1
    assert scan["pii_hit_total"] >= 1
    assert scan["pii_rules_version"] == "v1"
```

- [ ] **Step 2: 写 src/skillgap/quality_metrics.py**

```python
"""E5 数据质量指标（EVALUATION_PLAN §5：五指标 + 批次报告 + 全库扫描）。"""
from __future__ import annotations

import psycopg

from skillgap.ingest.pii import PII_RULES_VERSION
from skillgap.models import BatchReport

# 阈值（Pass / Warn / Block）——EVALUATION_PLAN §5.1
THRESHOLDS = {
    "duplicate_rate": (0.10, 0.25),
    "missing_field_rate": (0.0, 0.0),
    "invalid_jd_rate": (0.05, 0.15),
    "skill_extraction_error_rate": (0.03, 0.08),
}


def _rate(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def batch_metrics(report: BatchReport) -> dict:
    """批次指标：duplicate / invalid_jd / skill_extraction_error rate。"""
    extraction_attempts = report.inserted + report.extraction_failed
    return {
        "duplicate_rate": _rate(report.duplicates, report.total),
        "invalid_jd_rate": _rate(report.quarantined + report.rejected,
                                 report.total),
        "skill_extraction_error_rate": _rate(report.extraction_failed,
                                             extraction_attempts),
    }


def full_scan(conn: psycopg.Connection) -> dict:
    """全库扫描：missing_field_rate（DB 约束兜底应为 0）+ PII 命中聚合。"""
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job")
        total = cur.fetchone()["c"]
        # 来源九字段空值检查（NOT NULL 约束兜底；此处为 E5 显式口径）
        cur.execute(
            """SELECT count(*) AS c FROM job WHERE
               title IS NULL OR raw_text IS NULL OR source_id IS NULL OR
               source_type IS NULL OR collected_at IS NULL OR
               content_hash IS NULL OR data_quality IS NULL OR
               (source_type = 'public_job_page' AND source_url IS NULL) OR
               (source_type = 'user_submitted' AND consent_status IS NULL)""")
        missing = cur.fetchone()["c"]
        cur.execute(
            """SELECT count(*) AS c FROM job
               WHERE parsed_metadata ? 'pii_redaction'""")
        scan_count = cur.fetchone()["c"]
        cur.execute(
            """SELECT coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'phone')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'email')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'wechat')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'qq')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'contact')::int), 0)
               + coalesce(sum((parsed_metadata->'pii_redaction'->'hits'
               ->> 'id_card')::int), 0) AS c
               FROM job WHERE parsed_metadata ? 'pii_redaction'""")
        hits = cur.fetchone()["c"]
    return {
        "job_count": total,
        "missing_field_rate": _rate(missing, total),
        "pii_rules_version": PII_RULES_VERSION,
        "pii_scan_count": scan_count,
        "pii_hit_total": hits if hits is not None else 0,
    }


def quality_report(conn: psycopg.Connection) -> dict:
    """聚合视图（对齐 API §2.13 响应结构；manual_audit 由人工流程回填）。"""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT count(*) AS c FROM ingest_batch
               WHERE started_at::date = CURRENT_DATE""")
        batches_today = cur.fetchone()["c"]
    scan = full_scan(conn)
    return {
        "batches_today": batches_today,
        **scan,
        "pii_detection": {
            "rules_version": scan["pii_rules_version"],
            "scan_count": scan["pii_scan_count"],
            "hit_total": scan["pii_hit_total"],
            "manual_audit_pass": None,   # 人工抽查后回填（E5 §5.1 每月抽样）
        },
        "computed_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
    }
```

- [ ] **Step 3: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_quality_metrics.py -v
```
Expected: 3 passed

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/quality_metrics.py tests/test_quality_metrics.py
git commit -m "feat(phase2): e5 data quality metrics (batch + full scan + report)"
```

---

## Task 14: 频率统计空跑（S11 口径冻结）

**Files:**
- Create: `src/skillgap/stats.py`
- Test: `tests/test_stats.py`

- [ ] **Step 1: 写 tests/test_stats.py（口径 + 守门 + 置信度 + B1 排除）**

```python
from skillgap.ingest.pipeline import run_batch
from skillgap.stats import STATS_FILTER, skill_frequency
from tests.test_pipeline import _rec as make_rec


def _jobs(clean_db, n, consent="none", source="demo_dataset",
          source_type="dataset_builtin"):
    recs = []
    for i in range(n):
        r = make_rec()
        r.source.source_name = source
        r.source.source_type = source_type
        r.source.consent_status = consent
        r.title = f"AI 应用开发工程师 {i}"
        r.raw_text = f"编号{i}。" + r.raw_text  # 保证 hash 唯一
        recs.append(r)
    run_batch(clean_db, recs)


def test_stats_filter_constant_matches_frozen_spec():
    assert "j.status = 'active'" in STATS_FILTER
    assert "j.source_type <> 'user_submitted' OR j.consent_status = 'market_analysis'" \
        in STATS_FILTER.replace("!=", "<>")


def test_insufficient_sample_returns_marker(clean_db):
    _jobs(clean_db, 5)
    out = skill_frequency(clean_db, "china")
    assert out["status"] == "insufficient_sample"
    assert out["sample_size"] == 5


def test_frequency_counts_and_confidence(clean_db):
    _jobs(clean_db, 35)
    out = skill_frequency(clean_db, "china")
    assert out["status"] == "ok"
    assert out["confidence"] == "low"          # 30 <= 35 < 50
    rag = next(s for s in out["skills"] if s["canonical_name"] == "RAG")
    assert rag["jd_count"] == 35
    assert rag["frequency"] == 1.0


def test_unconsented_user_submissions_excluded(clean_db):
    # consent=none 的 user_submitted 不可能入库（B1 CHECK），但口径测试验证 SQL 本身
    _jobs(clean_db, 35)
    _jobs(clean_db, 5, consent="market_analysis", source="user_contribution",
          source_type="user_submitted")
    out = skill_frequency(clean_db, "china")
    assert out["sample_size"] == 40


def test_market_separation(clean_db):
    from skillgap.ingest.adzuna import AdzunaClient, fetch_adzuna
    import httpx
    PAGE = {"results": [{
        "id": "x1", "title": "AI Engineer",
        "description": "We need an LLM engineer with RAG experience. " * 4,
        "company": {"display_name": "Acme"},
        "location": {"display_name": "London"},
        "redirect_url": "https://example.com/x1",
    }]}

    def handler(request):
        return httpx.Response(200, json=PAGE)

    client = AdzunaClient("id", "key", http=httpx.Client(
        transport=httpx.MockTransport(handler)),
        base_url="https://adzuna.test")
    fetch_adzuna(clean_db, country="gb", query="LLM", max_results=5,
                 client=client)
    _jobs(clean_db, 5)
    out = skill_frequency(clean_db, "global")
    assert out["status"] == "ok"
    assert out["sample_size"] == 1        # 只含 Adzuna 1 条，不含中国 5 条
    zh = skill_frequency(clean_db, "china")
    assert zh["sample_size"] == 5         # 零混淆（验收红线）
```

- [ ] **Step 2: 写 src/skillgap/stats.py**

```python
"""S11 频率统计空跑（Phase 2：口径冻结；完整 Market Intelligence 属 Phase 4）。

口径（冻结，不得改动——DATA_MODEL §3 / DATA_PIPELINE S11 / B1 修复）：
  status='active' AND (source_type <> 'user_submitted' OR consent_status='market_analysis')
守门（ADR-008）：N < 30 不出统计；置信度 high>=200 / medium 50-200 / low 30-50。
本模块零 LLM 依赖（CI 静态检查目标之一）。
"""
from __future__ import annotations

import psycopg

STATS_FILTER = (
    "j.status = 'active' AND (j.source_type <> 'user_submitted' "
    "OR j.consent_status = 'market_analysis')"
)


def sample_size(conn: psycopg.Connection, market: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT count(*) AS c FROM job j WHERE j.market = %s "
            f"AND {STATS_FILTER}", (market,))
        return cur.fetchone()["c"]


def _confidence(n: int) -> str:
    if n >= 200:
        return "high"
    if n >= 50:
        return "medium"
    return "low"


def skill_frequency(conn: psycopg.Connection, market: str) -> dict:
    """空跑口径：技能频率 + 样本量 + 来源分布 + 置信度（Phase 4 冻结为快照）。"""
    n = sample_size(conn, market)
    if n < 30:
        return {"market": market, "sample_size": n,
                "status": "insufficient_sample"}

    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT s.canonical_name, count(DISTINCT js.job_id) AS jd_count
                FROM job_skill js
                JOIN job j ON j.id = js.job_id
                JOIN skill s ON s.id = js.skill_id
                WHERE j.market = %s AND {STATS_FILTER}
                GROUP BY s.canonical_name
                ORDER BY jd_count DESC, s.canonical_name""",
            (market,))
        rows = cur.fetchall()
        cur.execute(
            f"""SELECT ds.source_name, ds.trust_tier, count(*) AS c
                FROM job j JOIN data_source ds ON ds.id = j.source_id
                WHERE j.market = %s AND {STATS_FILTER}
                GROUP BY ds.source_name, ds.trust_tier ORDER BY c DESC""",
            (market,))
        dist = cur.fetchall()

    skills = [
        {"canonical_name": r["canonical_name"], "jd_count": r["jd_count"],
         "frequency": round(r["jd_count"] / n, 4)}
        for r in rows
    ]
    source_distribution = [
        {"source_name": r["source_name"], "trust_tier": r["trust_tier"],
         "count": r["c"], "share": round(r["c"] / n, 4)}
        for r in dist
    ]
    return {
        "market": market, "sample_size": n, "status": "ok",
        "confidence": _confidence(n),
        "skills": skills, "source_distribution": source_distribution,
        "stats_filter": STATS_FILTER,
    }
```

- [ ] **Step 3: 运行测试**

```powershell
.\.venv\Scripts\pytest tests/test_stats.py -v
```
Expected: 5 passed

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/stats.py tests/test_stats.py
git commit -m "feat(phase2): s11 frequency stats dry-run with frozen filter and sample gate"
```

---

## Task 15: CLI 整合（skillgap 命令全家桶）

**Files:**
- Create: `src/skillgap/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写 tests/test_cli.py（冒烟级：参数解析 + 各子命令可调用）**

```python
import json

from skillgap.cli import build_parser, main


def test_parser_subcommands():
    parser = build_parser()
    for cmd in ["db-upgrade", "seed", "ingest-adzuna", "import", "contribute",
                "delete-contribution", "quality-report", "stats",
                "quarantine-list", "raw-cleanup"]:
        ns = parser.parse_args([cmd] if cmd not in (
            "ingest-adzuna", "import", "contribute", "delete-contribution",
            "stats") else [cmd] + (
            ["--country", "gb", "--query", "LLM"] if cmd == "ingest-adzuna"
            else ["--file", "x.csv"] if cmd == "import"
            else ["--title", "t", "--file", "j.txt", "--consent"]
            if cmd == "contribute"
            else ["--code", "AB12-CD34"] if cmd == "delete-contribution"
            else ["--market", "china"]))
        assert ns.command == cmd


def test_stats_command_outputs_json(clean_db, capsys):
    rc = main(["stats", "--market", "china"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["market"] == "china"


def test_quality_report_command(clean_db, capsys):
    rc = main(["quality-report"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "pii_detection" in out and "missing_field_rate" in out
```

- [ ] **Step 2: 写 src/skillgap/cli.py**

```python
"""skillgap CLI——Phase 2 数据层入口（FastAPI 属后续 Phase）。

命令清单：
  db-upgrade / seed / import / ingest-adzuna / contribute /
  delete-contribution / quarantine-list / raw-cleanup / quality-report / stats
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skillgap import db
from skillgap.config import settings
from skillgap.ingest.adzuna import fetch_adzuna
from skillgap.ingest.contribute import contribute_jd, delete_contribution
from skillgap.ingest.importer import parse_file
from skillgap.ingest.pipeline import run_batch
from skillgap.quality_metrics import quality_report
from skillgap.stats import skill_frequency
from skillgap.taxonomy.seed import seed_all


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="skillgap")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("db-upgrade", help="应用未执行的 SQL 迁移")
    sub.add_parser("seed", help="词表 v1 + 来源注册表建档（幂等）")

    p_ing = sub.add_parser("ingest-adzuna", help="拉取 Adzuna 海外岗位（Global）")
    p_ing.add_argument("--country", default="gb")
    p_ing.add_argument("--query", default="LLM OR RAG OR AI engineer")
    p_ing.add_argument("--max-results", type=int, default=500)

    p_imp = sub.add_parser("import", help="CSV/JSON 批量导入")
    p_imp.add_argument("--file", required=True)

    p_con = sub.add_parser("contribute", help="匿名贡献 JD（opt-in）")
    p_con.add_argument("--title", required=True, help="岗位标题")
    p_con.add_argument("--file", required=True, help="JD 文本文件")
    p_con.add_argument("--source-hint", default="other")
    p_con.add_argument("--consent", action="store_true",
                       help="明确同意匿名贡献（必须显式传入）")

    p_del = sub.add_parser("delete-contribution", help="凭 deletion_code 删除贡献")
    p_del.add_argument("--code", required=True)

    sub.add_parser("quarantine-list", help="查看隔离队列")
    sub.add_parser("raw-cleanup", help="清理 7 天前的 raw 暂存（DATA_GOVERNANCE §5）")

    sub.add_parser("quality-report", help="E5 数据质量报告（JSON）")

    p_st = sub.add_parser("stats", help="频率统计空跑（S11 口径）")
    p_st.add_argument("--market", choices=["china", "global"], default="china")

    return p


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = db.connect()

    try:
        if args.command == "db-upgrade":
            _print(db.upgrade(conn))
        elif args.command == "seed":
            seed_all(conn)
            _print({"status": "seeded"})
        elif args.command == "ingest-adzuna":
            report = fetch_adzuna(conn, country=args.country, query=args.query,
                                  max_results=args.max_results)
            _print(report.model_dump())
        elif args.command == "import":
            records = parse_file(args.file)
            report = run_batch(conn, records)
            _print(report.model_dump())
        elif args.command == "contribute":
            jd_text = Path(args.file).read_text(encoding="utf-8")
            result = contribute_jd(conn, jd_text=jd_text, consent=args.consent,
                                   title=args.title,
                                   source_hint=args.source_hint)
            _print({
                "job_id": result.job_id,
                "deduplicated": result.deduplicated,
                "pii_redaction": result.pii_redaction,
                "deletion_code": result.deletion_code,
                "note": "deletion_code 仅本次展示，请自行保存",
            })
        elif args.command == "delete-contribution":
            ok = delete_contribution(conn, args.code)
            print("204 deleted" if ok else "404 not_found（code 不存在或已删除）")
            return 0 if ok else 1
        elif args.command == "quarantine-list":
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, status, error, created_at FROM raw_jobs "
                    "WHERE status IN ('quarantined', 'failed') "
                    "ORDER BY created_at DESC LIMIT 50")
                _print(cur.fetchall())
        elif args.command == "raw-cleanup":
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM raw_jobs WHERE created_at < now() - "
                    "interval '7 days' RETURNING id")
                _print({"deleted": cur.rowcount})
            conn.commit()
        elif args.command == "quality-report":
            _print(quality_report(conn))
        elif args.command == "stats":
            _print(skill_frequency(conn, args.market))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
```

注意：`test_cli.py` 中 `stats` / `quality-report` 命令测试需要 DATABASE_URL 指向测试库——执行时通过 `os.environ` monkeypatch 或在 conftest 里为 CLI 测试设置环境（`monkeypatch.setenv("DATABASE_URL", TEST_URL)` 后重建 settings）。**实现时给 `db.connect()` 加 `url` 参数透传并在测试中直接调用 `main` 前设置环境变量。**

- [ ] **Step 3: 运行 + 冒烟**

```powershell
.\.venv\Scripts\pytest tests/test_cli.py -v
.\.venv\Scripts\skillgap db-upgrade
.\.venv\Scripts\skillgap seed
.\.venv\Scripts\skillgap import --file data/collect_template.csv
.\.venv\Scripts\skillgap stats --market china
.\.venv\Scripts\skillgap quality-report
```
Expected: 模板 2 条导入成功（inserted=2）；stats 输出 `insufficient_sample`（N=2 < 30）；quality-report 输出 JSON。

- [ ] **Step 4: Commit**

```powershell
git add src/skillgap/cli.py tests/test_cli.py
git commit -m "feat(phase2): skillgap cli (import/ingest/contribute/quality/stats)"
```

---

## Task 16: 数据来源记录规范（DATA_COLLECTION.md）+ 首批收集启动

**Files:**
- Create: `docs/DATA_COLLECTION.md`（ROADMAP Phase 2 交付物"数据来源记录规范"）

- [ ] **Step 1: 写 docs/DATA_COLLECTION.md**

````markdown
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
````

- [ ] **Step 2: Commit**

```powershell
git add docs/DATA_COLLECTION.md
git commit -m "docs(phase2): data collection spec and batch protocol"
```

**说明：** 200-300 条 JD 的人工收集（约 10 小时）是用户本人的体力活，本计划只交付规范、模板与校准流程；首批 50 条建议在管道全绿后开始（ROADMAP 建议"管道与 Schema 先行，数据收集与管道调试交错"）。

---

## Task 17: 全量验证 + Phase 2 六维自检 + 文档收尾

**Files:**
- Modify: `docs/ROADMAP.md`（追加 Phase 2 Review 记录）
- Create: 根目录 `PHASE_2_REVIEW.md`（按 PHASE_1_REVIEW 惯例，简版）

- [ ] **Step 1: 全量测试**

```powershell
docker compose up -d postgres redis
.\.venv\Scripts\pytest -v
```
Expected: 全部 passed（纯单测无需 DB；集成测试需 compose postgres 运行中）

- [ ] **Step 2: 验收清单逐项核对（ROADMAP Phase 2 验收）**

| 验收项 | 验证方式 |
|---|---|
| 导入报告完整（新增/重复/失败计数） | `skillgap import` 输出 + test_pipeline.py::test_run_batch_report_counts |
| PII 规则单测通过（含边界用例） | test_pii.py 11 项（含校验位/误报/防重叠/fail-closed） |
| Adzuna 入库 market=global 无污染 | test_adzuna.py::test_fetch_adzuna_pipeline_integration + test_stats.py::test_market_separation |
| 抽样 20 条人工核对字段 | DATA_COLLECTION.md §4 流程（导入真实数据后执行） |
| 频率统计空跑通（SQL 口径确定） | test_stats.py 全部 + STATS_FILTER 常量冻结 |
| docker compose up 数据库就绪 | Task 2 healthcheck |

- [ ] **Step 3: 生成 PHASE_2_REVIEW.md（六维自检，执行时以实际结果填写指标数值）**

模板骨架（验收数字以实际跑分为准）：

```markdown
# PHASE_2_REVIEW —— Phase 2 完成自检（六维）

> 状态：PASS / PASS WITH RISKS（以实际验证结果判定）
> 验收：ROADMAP Phase 2 六项验收逐项核验结果（见 §2 表）

## 1. 交付物清单（对照 ROADMAP Phase 2 产出）
- [ ] PG Schema（全部约束）+ pgvector 预留表（不建索引）
- [ ] Ingestion 管道 S1-S10（Adzuna/CSV/JSON/贡献/PII/去重/质检 quarantine）
- [ ] E5 数据质量指标（批次报告）
- [ ] 词表 v1 建档（skill/alias/relation 种子——评审 M3 关闭）
- [ ] 数据来源记录规范（DATA_COLLECTION.md）+ 收集模板
- [ ] ADR-010 + DECISION_LOG D-2026-08-31-10

## 2. 六维自检
### Product（解决什么）数据管道可用，200-300 条收集可以开跑
### Engineering（过度设计？）表只多不少：18 张表全部来自 DATA_MODEL §2 + 3 张管道支撑表（raw_jobs/ingest_batch/checkpoint+log），无自加业务表
### AI（LLM 滥用？）本阶段零 LLM 依赖；S8 以协议接口预留（Phase 3 接入）
### Data（真实可溯？）九字段 DB 强制；content_hash 唯一；市场分离双保险；B1 统计口径 SQL 冻结
### Evaluation（可验证？）E5 三项自动指标 + 阈值表；测试 N 项全绿；回归历史入 ingest_batch
### Resume（可讲什么）"我实现了带 PII 三层防线与 fail-closed 语义的数据管道，统计口径以 SQL 常量冻结可复现"

## 3. 遗留与移交 Phase 3
- S8 LLM 实现（LLM Gateway + Structured Output + 重试）
- extraction_status=pending 的 job 抽取回填命令
- 英文程度词映射（评审 M1，Phase 3 冻结抽取 Schema 时一并）
- 首批 50 条收集与词表校准（用户执行，DATA_COLLECTION §3）
```

- [ ] **Step 4: ROADMAP.md 末尾追加 Phase 2 Review 记录（六维结论简版，链接 PHASE_2_REVIEW.md）**

- [ ] **Step 5: 最终 Commit**

```powershell
git add docs/ROADMAP.md PHASE_2_REVIEW.md
git commit -m "docs(phase2): phase 2 review record and roadmap update"
```

---

## 计划自检（Self-Review 结论）

1. **规格覆盖**：PG Schema 全表+约束（Task 3 ↔ DATA_MODEL §2/§3）；S1-S10 每步有实现（S1=Task 10/11/12，S2=pipeline._stage_raw，S3/S6=Task 6，S4/S5=Task 5，S7=Task 6，S8/S9=Task 8，S10=Task 9，S11 空跑=Task 14）；E5=Task 13；词表 v1+M3 关闭=Task 7；收集规范=Task 16；验收 6 项全部映射（Task 17 §2）。差距：无。
2. **占位符扫描**：Task 12/Task 15 的"实现说明"是对草稿的两处显式修正指令（非 TBD），执行时按修正版落实；PHASE_2_REVIEW 的指标数值依赖执行结果，已注明"以实际跑分为准"。
3. **类型一致性**：`BatchReport`/`RawRecord`/`SourceFields` 在 Task 4 定义、Task 9-13 使用一致；`RecordOutcome`/`QualityVerdict`/`PIIFinding` 各自定义不外泄；`content_hash` 归一化函数在 normalize.py 单一定义（Task 6），Task 12 复用导入。
4. **已知执行期修正点**（写代码时直接落实，不要照抄草稿）：
   - Task 9 `pipeline.py` 中 `_stage_raw` 未被调用（S2 暂存由 `_mark_raw` 在各分支统一落 raw_jobs）——实现时删掉 `_stage_raw` 或在 process_record 开头调用一次并在结束时更新状态；
   - Task 10 `_from_rows` 行号逻辑按"实现说明"简化；
   - Task 12 `parsed_source_hint` 按"实现说明"改为 parsed_metadata；
   - Task 15 CLI 测试需将 DATABASE_URL 指向测试库。
