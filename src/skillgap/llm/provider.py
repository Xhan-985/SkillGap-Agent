"""LLM Provider 抽象 + OpenAI-compatible 单实现（httpx 直调，零 SDK 依赖）。

Gateway 的底层：只管 HTTP（鉴权/重试/超时），不管业务 Schema。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import httpx

_sleep = time.sleep  # 测试可注入
RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504)


class LLMError(RuntimeError):
    """LLM 调用层错误（网络/HTTP/超时/结构异常）——与抽取层校验失败区分。"""


@dataclass
class LLMResponse:
    content: str
    total_tokens: int = 0
    model: str = ""


class LLMProvider(Protocol):
    def chat(self, messages: list[dict],
             response_json: bool = False) -> LLMResponse: ...


class OpenAICompatibleProvider:
    """DeepSeek 及一切 OpenAI-compatible 服务（用户决策 2026-08-31：DeepSeek）。"""

    def __init__(self, base_url: str, api_key: str, model: str,
                 http: httpx.Client | None = None, timeout: float = 60.0,
                 max_retries: int = 2):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.http = http or httpx.Client(timeout=timeout)
        self.max_retries = max_retries

    def chat(self, messages: list[dict],
             response_json: bool = False) -> LLMResponse:
        payload: dict = {"model": self.model, "messages": messages,
                         "temperature": 0.0}   # 抽取任务要求确定性
        if response_json:
            payload["response_format"] = {"type": "json_object"}
        last: str = ""
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.http.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.HTTPError as e:
                last = f"网络错误: {e}"
                if attempt < self.max_retries:
                    _sleep(2 ** attempt)
                    continue
                raise LLMError(
                    f"LLM 调用失败（重试 {self.max_retries} 次）: {last}")
            if resp.status_code in RETRYABLE_STATUS:
                last = f"HTTP {resp.status_code}"
                if attempt < self.max_retries:
                    delay = resp.headers.get("Retry-After")
                    if delay:
                        try:    # RFC 7231 允许 HTTP-date 格式，回退默认退避
                            backoff = min(float(delay), 30.0)
                        except ValueError:
                            backoff = 2 ** attempt
                    else:
                        backoff = 2 ** attempt
                    _sleep(backoff)
                    continue
                raise LLMError(
                    f"LLM 调用失败（重试 {self.max_retries} 次）: {last}")
            if resp.status_code != 200:
                raise LLMError(
                    f"LLM HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            try:
                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    total_tokens=(data.get("usage") or {}).get(
                        "total_tokens", 0),
                    model=data.get("model", self.model),
                )
            except (KeyError, IndexError, TypeError) as e:
                raise LLMError(f"LLM 响应结构异常: {e}")
        raise LLMError(f"LLM 调用失败（重试 {self.max_retries} 次）: {last}")
