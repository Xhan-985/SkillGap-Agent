"""LLM Gateway：缓存查询 → provider 调用（重试）→ 缓存写入。

对上层暴露 chat(messages)：消息级 API；业务 Schema 校验在 extract 层。
缓存键 = sha256(model + 规范化 messages)——同模型同输入幂等（ADR-009 成本缓解）。
"""
from __future__ import annotations

import hashlib
import json

import psycopg

from skillgap.llm.provider import LLMProvider, LLMResponse


def _canonical_messages(messages: list[dict]) -> str:
    return json.dumps(messages, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def cache_key(model: str, messages: list[dict]) -> str:
    return hashlib.sha256(
        (model + "|" + _canonical_messages(messages)).encode("utf-8")
    ).hexdigest()


class LLMGateway:
    def __init__(self, conn: psycopg.Connection, provider: LLMProvider,
                 prompt_version: str):
        self.conn = conn
        self.provider = provider
        self.prompt_version = prompt_version

    def chat(self, messages: list[dict],
             response_json: bool = False) -> LLMResponse:
        key = cache_key(self.provider.model, messages)
        row = self._cache_get(key)
        if row is not None:
            cached = row["response"]
            return LLMResponse(content=cached["content"],
                               total_tokens=cached.get("total_tokens", 0),
                               model=self.provider.model)
        resp = self.provider.chat(messages, response_json=response_json)
        self._cache_put(key, resp)
        return resp

    def _cache_get(self, key: str):
        with self.conn.cursor() as cur:
            cur.execute("SELECT response FROM llm_cache WHERE cache_key = %s",
                        (key,))
            return cur.fetchone()

    def _cache_put(self, key: str, resp: LLMResponse) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO llm_cache
                   (cache_key, response, provider, model, prompt_version)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (cache_key) DO NOTHING""",
                (key,
                 json.dumps({"content": resp.content,
                             "total_tokens": resp.total_tokens},
                            ensure_ascii=False),
                 type(self.provider).__name__, self.provider.model,
                 self.prompt_version))
        self.conn.commit()
