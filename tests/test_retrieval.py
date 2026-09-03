"""RAG 引用层测试（Fake embedding，零真实 API 调用）。"""
from __future__ import annotations

import zlib

from skillgap.llm.embedding import (
    EmbeddingResponse, OpenAICompatibleEmbedding, to_vector_literal,
)
from skillgap.retrieval.service import index_evidence, semantic_search

DIM = 1024


class FakeEmbedding:
    """确定性伪 embedding：字符 bigram → crc32 桶累计 + 归一化。

    语义上：字符重叠多的文本余弦相似度更高（足够测试排序/过滤断言）。
    """

    def embed(self, texts):
        vecs = []
        for t in texts:
            v = [0.0] * DIM
            low = t.lower()
            for i in range(len(low) - 1):
                v[zlib.crc32(low[i:i + 2].encode()) % DIM] += 1.0
            norm = sum(x * x for x in v) ** 0.5
            vecs.append([x / norm for x in v] if norm else v)
        return EmbeddingResponse(embeddings=vecs)


def _insert_jobs(clean_db, n, market):
    """插 n 条 job + 每条 1 行 MCP 证据；返回 job_id 列表。"""
    from tests.test_schema import _insert_job, _job_kwargs, _source
    sid = _source(clean_db)
    ids = []
    with clean_db.cursor() as cur:
        for i in range(n):
            jid = _insert_job(
                clean_db, **_job_kwargs(
                    sid, title=f"AI 平台工程师 {i}", market=market,
                    content_hash=f"h-{market}-{i}"))
            cur.execute(
                """INSERT INTO job_skill (job_id, skill_id, importance,
                   evidence_text, extracted_by)
                   SELECT %s, id, 'must_have',
                          '熟悉 MCP（模型上下文协议）工具链开发',
                          'manual'
                   FROM skill WHERE canonical_name = 'MCP'""",
                (jid,))
            ids.append(jid)
    clean_db.commit()
    return ids


# ---------- 向量字面量 ----------

def test_to_vector_literal_format():
    assert to_vector_literal([1.0, 0.5]) == "[1.000000,0.500000]"


def test_provider_payload_omits_temperature():
    """reasoner 兼容：temperature=None 时 payload 不含该键。"""
    import httpx
    from skillgap.llm.provider import OpenAICompatibleProvider

    captured = {}

    class _StubHttp(httpx.Client):
        def post(self, url, **kw):
            captured.update(kw.get("json") or {})

            class _R:
                status_code = 200

                def json(self):
                    return {"choices": [{"message": {"content": "{}"}}],
                            "usage": {}, "model": "m"}

            return _R()

    p = OpenAICompatibleProvider(base_url="https://x", api_key="k",
                                 model="reasoner", http=_StubHttp(),
                                 temperature=None)
    p.chat([{"role": "user", "content": "hi"}])
    assert "temperature" not in captured
    p2 = OpenAICompatibleProvider(base_url="https://x", api_key="k",
                                  model="chat", http=_StubHttp())
    p2.chat([{"role": "user", "content": "hi"}])
    assert captured["temperature"] == 0.0


# ---------- index / search（clean_db 已跑 migration 004） ----------

def test_index_evidence_fills_and_idempotent(clean_db):
    _insert_jobs(clean_db, 3, "china")
    n1 = index_evidence(clean_db, provider=FakeEmbedding())
    assert n1 == 3
    n2 = index_evidence(clean_db, provider=FakeEmbedding())
    assert n2 == 0                    # 幂等：只补空行
    nulls = clean_db.execute(
        "SELECT count(*) AS n FROM job_skill"
        " WHERE evidence_embedding IS NULL").fetchone()["n"]
    assert nulls == 0


def test_semantic_search_returns_traceable_rows(clean_db):
    _insert_jobs(clean_db, 3, "china")
    index_evidence(clean_db, provider=FakeEmbedding())
    rows = semantic_search(clean_db, "MCP 模型上下文协议",
                           provider=FakeEmbedding(), top_k=2)
    assert len(rows) == 2
    for r in rows:
        assert r["skill"] == "MCP"
        assert r["job_id"]
        assert r["importance"] == "must_have"
        assert "MCP" in r["evidence_text"]
        assert 0.0 <= r["similarity"] <= 1.0001
    # 余弦降序
    sims = [r["similarity"] for r in rows]
    assert sims == sorted(sims, reverse=True)


def test_semantic_search_market_filter(clean_db):
    _insert_jobs(clean_db, 2, "china")
    _insert_jobs(clean_db, 2, "global")
    index_evidence(clean_db, provider=FakeEmbedding())
    rows = semantic_search(clean_db, "模型上下文协议",
                           provider=FakeEmbedding(), market="global")
    assert len(rows) == 2
    jobs = clean_db.execute(
        "SELECT id, market FROM job").fetchall()
    market_by_id = {j["id"]: j["market"] for j in jobs}
    assert all(market_by_id[r["job_id"]] == "global" for r in rows)


def test_semantic_search_empty_query_raises(clean_db):
    import pytest
    with pytest.raises(ValueError, match="不能为空"):
        semantic_search(clean_db, "  ", provider=FakeEmbedding())


def test_provider_without_key_raises_clean(monkeypatch):
    """未配置 EMBEDDING_API_KEY：明确报错不臆造（ADR-008 同款纪律）。"""
    import pytest

    monkeypatch.setattr(
        "skillgap.config.settings.embedding_api_key", "")
    with pytest.raises(ValueError, match="EMBEDDING_API_KEY"):
        index_evidence(None)          # provider 未注入 → 走 _provider() 守卫
