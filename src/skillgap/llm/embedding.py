"""Embedding Provider（OpenAI-compatible /embeddings 端点，httpx 直调）。

RAG 引用层专用（用户决策 2026-09-04：硅基流动 BAAI/bge-m3，1024 维）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

_sleep = time.sleep
RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504)


class EmbeddingError(RuntimeError):
    """Embedding 调用层错误（网络/HTTP/结构异常）。"""


@dataclass
class EmbeddingResponse:
    embeddings: list[list[float]]
    total_tokens: int = 0
    model: str = ""


class OpenAICompatibleEmbedding:
    """bge-m3 及一切 OpenAI-compatible embedding 服务。"""

    def __init__(self, base_url: str, api_key: str, model: str,
                 http: httpx.Client | None = None, timeout: float = 30.0,
                 max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http = http or httpx.Client(timeout=timeout)
        self.max_retries = max_retries

    def embed(self, texts: list[str]) -> EmbeddingResponse:
        if not texts:
            return EmbeddingResponse(embeddings=[])
        payload = {"model": self.model, "input": list(texts)}
        last = ""
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.http.post(
                    f"{self.base_url}/embeddings", json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"})
            except httpx.HTTPError as e:
                last = f"网络错误: {e}"
                if attempt < self.max_retries:
                    _sleep(2 ** attempt)
                    continue
                raise EmbeddingError(
                    f"embedding 调用失败（重试 {self.max_retries} 次）: {last}")
            if resp.status_code in RETRYABLE_STATUS:
                last = f"HTTP {resp.status_code}"
                if attempt < self.max_retries:
                    _sleep(2 ** attempt)
                    continue
                raise EmbeddingError(
                    f"embedding 调用失败（重试 {self.max_retries} 次）: {last}")
            if resp.status_code != 200:
                raise EmbeddingError(
                    f"embedding HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            try:
                ordered = sorted(data["data"], key=lambda d: d["index"])
                return EmbeddingResponse(
                    embeddings=[d["embedding"] for d in ordered],
                    total_tokens=(data.get("usage") or {}).get(
                        "total_tokens", 0),
                    model=data.get("model", self.model))
            except (KeyError, IndexError, TypeError) as e:
                raise EmbeddingError(f"embedding 响应结构异常: {e}")
        raise EmbeddingError(
            f"embedding 调用失败（重试 {self.max_retries} 次）: {last}")


def to_vector_literal(vec: list[float]) -> str:
    """pgvector 文本字面量（零依赖传参：参数按 text 传，SQL 侧 %s::vector）。"""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
