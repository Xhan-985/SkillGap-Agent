import httpx
import pytest

from skillgap.llm import provider as pm
from skillgap.llm.provider import LLMResponse, OpenAICompatibleProvider

OK_BODY = {"choices": [{"message": {"content": '{"skills": []}'}}],
           "usage": {"total_tokens": 120}, "model": "m"}


def _provider(handler, **kw):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    defaults = dict(base_url="https://llm.test", api_key="k", model="m",
                    http=http, timeout=5.0)
    defaults.update(kw)
    return OpenAICompatibleProvider(**defaults)


def test_chat_returns_response_and_sends_bearer():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["Authorization"]
        seen["url"] = str(req.url)
        return httpx.Response(200, json=OK_BODY)

    resp = _provider(handler).chat(
        messages=[{"role": "user", "content": "hi"}], response_json=True)
    assert isinstance(resp, LLMResponse)
    assert resp.content == '{"skills": []}'
    assert resp.total_tokens == 120
    assert resp.model == "m"
    assert seen["auth"] == "Bearer k"
    assert "chat/completions" in seen["url"]


def test_429_retry_then_success(monkeypatch):
    monkeypatch.setattr(pm, "_sleep", lambda s: None)
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["i"] += 1
        return httpx.Response(429) if n["i"] == 1 else httpx.Response(200, json=OK_BODY)

    resp = _provider(handler).chat([{"role": "user", "content": "x"}])
    assert resp.content == '{"skills": []}' and n["i"] == 2


def test_retry_after_header_respected(monkeypatch):
    delays = []
    monkeypatch.setattr(pm, "_sleep", delays.append)
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"})
        return httpx.Response(200, json=OK_BODY)

    _provider(handler).chat([{"role": "user", "content": "x"}])
    assert delays == [1.5]


def test_persistent_error_raises_llmerror(monkeypatch):
    monkeypatch.setattr(pm, "_sleep", lambda s: None)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(pm.LLMError, match="LLM 调用失败"):
        _provider(handler).chat([{"role": "user", "content": "x"}])


def test_response_json_flag_forces_json_object():
    import json as j
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = j.loads(req.content)
        return httpx.Response(200, json=OK_BODY)

    _provider(handler).chat([{"role": "user", "content": "x"}], response_json=True)
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["temperature"] == 0.0


def test_malformed_response_raises_llmerror():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    with pytest.raises(pm.LLMError, match="响应结构异常"):
        _provider(handler).chat([{"role": "user", "content": "x"}])


def test_network_error_retries_then_raises(monkeypatch):
    monkeypatch.setattr(pm, "_sleep", lambda s: None)

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(pm.LLMError, match="网络错误"):
        _provider(handler).chat([{"role": "user", "content": "x"}])


def test_no_sleep_on_final_retryable_attempt(monkeypatch):
    """末次尝试遇可重试状态码：直接抛 LLMError，不再无谓退避。"""
    sleeps: list[float] = []
    monkeypatch.setattr(pm, "_sleep", sleeps.append)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(pm.LLMError, match="LLM 调用失败"):
        _provider(handler).chat([{"role": "user", "content": "x"}])
    assert sleeps == [1, 2]      # 2**0、2**1；末次（第 3 次）不 sleep


def test_retry_after_http_date_falls_back(monkeypatch):
    """RFC 7231 允许 Retry-After 为 HTTP-date：解析失败回退默认退避，不抛 ValueError。"""
    sleeps: list[float] = []
    monkeypatch.setattr(pm, "_sleep", sleeps.append)
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["i"] += 1
        if n["i"] == 1:
            return httpx.Response(429, headers={
                "Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
        return httpx.Response(200, json=OK_BODY)

    resp = _provider(handler).chat([{"role": "user", "content": "x"}])
    assert resp.content == '{"skills": []}'
    assert sleeps == [1]          # HTTP-date 不可解析 → 回退 2**0 = 1
