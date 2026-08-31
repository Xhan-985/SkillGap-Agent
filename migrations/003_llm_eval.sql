-- 003: Phase 3 —— LLM 响应缓存（ADR-009：content_hash 缓存缓解成本）+ 评测回归历史（EVALUATION_PLAN §6）
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key      TEXT PRIMARY KEY,           -- sha256(model + messages canonical)
    response       JSONB NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS eval_run (
    id             SERIAL PRIMARY KEY,
    eval_type      TEXT NOT NULL CHECK (eval_type IN ('skill_extraction','matching','recommendation','data_quality')),
    dataset_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model          TEXT NOT NULL,
    metrics        JSONB NOT NULL,             -- 全部指标 + 版本三元组 + 环境
    sample_size    INT NOT NULL,
    verdict        TEXT NOT NULL CHECK (verdict IN ('pass','warn','block')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
