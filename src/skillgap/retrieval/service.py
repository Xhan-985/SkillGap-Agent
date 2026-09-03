"""RAG 引用层（Phase 8 D10——D-2026-09-04-15 复议提前落地）。

检索单位 = job_skill 证据行：语义命中即得 (job, skill, evidence_text)
精确溯源。与 skill-evidence SQL 精确版（alias 命中）互补——本层管语义
变体（"模型上下文协议" → MCP）。

embedding 通道：OpenAI-compatible（用户决策 2026-09-04 硅基流动
BAAI/bge-m3，1024 维，migration 004）。
"""
from __future__ import annotations

from psycopg import Connection

from skillgap.llm.embedding import (
    OpenAICompatibleEmbedding, to_vector_literal,
)

# embed 文本 = 技能名 + 证据（带技能锚点，检索时更聚焦）
_EMBED_TEMPLATE = "{skill}: {evidence}"


def _provider() -> OpenAICompatibleEmbedding:
    from skillgap.config import settings
    if not settings.embedding_api_key:
        raise ValueError(
            "未配置 EMBEDDING_API_KEY（.env 或环境变量；"
            "推荐硅基流动 BAAI/bge-m3）")
    return OpenAICompatibleEmbedding(
        base_url=settings.embedding_base_url,
        api_key=settings.embedding_api_key,
        model=settings.embedding_model,
        timeout=settings.embedding_timeout)


def index_evidence(conn: Connection, provider=None, batch_size: int = 64,
                   limit: int | None = None) -> int:
    """回填 evidence_embedding IS NULL 的证据行，返回本次索引行数。

    幂等：只补空行；重跑只处理增量。"""
    prov = provider or _provider()
    q = ("""SELECT js.id, s.canonical_name, js.evidence_text
             FROM job_skill js JOIN skill s ON s.id = js.skill_id
            WHERE js.evidence_embedding IS NULL
            ORDER BY js.id""")
    with conn.cursor() as cur:
        cur.execute(q + (" LIMIT %s" % limit if limit else ""))
        rows = cur.fetchall()
    done = 0
    for start in range(0, len(rows), batch_size):
        chunk = rows[start:start + batch_size]
        texts = [_EMBED_TEMPLATE.format(
            skill=r["canonical_name"], evidence=r["evidence_text"])
            for r in chunk]
        resp = prov.embed(texts)
        with conn.cursor() as cur:
            for r, vec in zip(chunk, resp.embeddings):
                cur.execute(
                    "UPDATE job_skill SET evidence_embedding = %s::vector"
                    " WHERE id = %s",
                    (to_vector_literal(vec), r["id"]))
        conn.commit()
        done += len(chunk)
    return done


def semantic_search(conn: Connection, query: str, provider=None,
                    market: str | None = None, top_k: int = 5) -> list[dict]:
    """语义检索：query → 证据行 Top-K（含 job/skill 溯源与相似度）。"""
    if not query.strip():
        raise ValueError("查询不能为空")
    prov = provider or _provider()
    qvec = prov.embed([query]).embeddings[0]
    sql = """SELECT s.canonical_name AS skill, js.job_id, j.title,
                    js.importance, js.evidence_text,
                    1 - (js.evidence_embedding <=> %s::vector) AS similarity
             FROM job_skill js
             JOIN skill s ON s.id = js.skill_id
             JOIN job j ON j.id = js.job_id
             WHERE js.evidence_embedding IS NOT NULL"""
    params: list = [to_vector_literal(qvec)]
    if market:
        sql += " AND j.market = %s"
        params.append(market)
    sql += " ORDER BY js.evidence_embedding <=> %s::vector LIMIT %s"
    # cosine 距离参数复用第一个占位符的字面量
    params.append(params[0])
    params.append(top_k)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
