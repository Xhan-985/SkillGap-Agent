-- 004_rag_evidence.sql — Phase 8 RAG 引用层（D10；D-2026-09-04-15 复议提前落地）
-- 检索单位 = job_skill 证据行（非整条 JD）：命中即得 (job, skill, evidence_text)
-- 精确溯源，与 skill-evidence SQL 版互补（语义变体检索："模型上下文协议"→MCP）
ALTER TABLE job_skill
    ADD COLUMN IF NOT EXISTS evidence_embedding vector(1024);

-- bge-m3 1024 维，cosine 距离（嵌入已归一化时与内积等价）
CREATE INDEX IF NOT EXISTS idx_job_skill_evidence_embedding
    ON job_skill USING hnsw (evidence_embedding vector_cosine_ops);
