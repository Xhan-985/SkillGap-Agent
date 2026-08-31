import httpx
import pytest

from skillgap.llm import provider as pm
from skillgap.llm.gateway import LLMGateway, cache_key
from skillgap.llm.provider import LLMError, OpenAICompatibleProvider

OK = {"choices": [{"message": {"content": '{"ok": 1}'}}],
      "usage": {"total_tokens": 10}, "model": "m"}
MSGS = [{"role": "user", "content": "extract: 你好"}]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(pm, "_sleep", lambda s: None)


def _gateway(clean_db, handler, model="m"):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://llm.test", "k", model, http=http)
    return LLMGateway(clean_db, provider=p, prompt_version="v1")


def test_cache_key_deterministic_and_model_scoped():
    k1 = cache_key("m", MSGS)
    k2 = cache_key("m", list(MSGS))
    k3 = cache_key("other", MSGS)
    assert k1 == k2 and k1 != k3 and len(k1) == 64


def test_cache_key_preserves_message_order():
    """多消息顺序不同 → 键不同（canonical 保留消息顺序，仅排序 JSON 键）。"""
    two = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
    k1 = cache_key("m", two)
    k2 = cache_key("m", two[::-1])
    assert k1 != k2


def test_first_call_hits_provider_and_caches(clean_db):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=OK)

    gw = _gateway(clean_db, handler)
    r1 = gw.chat(MSGS, response_json=True)
    r2 = gw.chat(MSGS, response_json=True)
    assert r1.content == r2.content == '{"ok": 1}'
    assert calls["n"] == 1          # 第二次命中缓存
    with clean_db.cursor() as cur:
        cur.execute("SELECT provider, model, prompt_version, response FROM llm_cache")
        row = cur.fetchone()
    assert row["model"] == "m" and row["prompt_version"] == "v1"
    assert row["response"]["total_tokens"] == 10


def test_cached_response_not_model_confused(clean_db):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=OK)

    _gateway(clean_db, handler, model="m").chat(MSGS)
    _gateway(clean_db, handler, model="m2").chat(MSGS)   # 不同 cache_key
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM llm_cache")
        assert cur.fetchone()["c"] == 2


def test_provider_error_not_cached(clean_db):
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["i"] += 1
        if n["i"] <= 3:            # max_retries=2 → 3 次尝试全 500
            return httpx.Response(500)
        return httpx.Response(200, json=OK)

    gw = _gateway(clean_db, handler)
    with pytest.raises(LLMError):
        gw.chat(MSGS)
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM llm_cache")
        assert cur.fetchone()["c"] == 0


def test_cache_survives_new_gateway_instance(clean_db):
    """缓存为 DB 持久层语义：新 gateway 实例仍命中（成本缓解目标）。"""
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=OK)

    _gateway(clean_db, handler).chat(MSGS)
    calls = {"n": 0}

    def counting(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=OK)

    _gateway(clean_db, counting).chat(MSGS)
    assert calls["n"] == 0          # 完全命中缓存，provider 未被调用
