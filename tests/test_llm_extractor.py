import httpx
import pytest

from skillgap.extract.llm_extractor import ExtractionFailed, LLMSkillExtractor
from skillgap.llm.gateway import LLMGateway
from skillgap.llm.provider import OpenAICompatibleProvider

JD = "岗位职责：搭建 RAG 检索链路。要求：1-3年大模型应用开发经验。"

GOOD = """{"skills": [{"raw_name": "RAG", "importance": "must_have",
 "intensity": "熟悉", "evidence_text": "搭建 RAG 检索链路"}],
 "soft_requirements": [{"type": "experience", "value": "1-3年",
 "evidence_text": "1-3年大模型应用开发经验"}]}"""

GOOD_SOFTLESS = '{"skills": [{"raw_name": "RAG", "importance": "must_have", "evidence_text": "搭建 RAG 检索链路"}]}'


def _extractor(clean_db, content: str):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [
            {"message": {"content": content}}],
            "usage": {"total_tokens": 50}, "model": "m"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://t", "k", "m", http=http)
    return LLMSkillExtractor(LLMGateway(clean_db, provider=p,
                                        prompt_version="v1"))


def test_extract_ok(clean_db):
    anns = _extractor(clean_db, GOOD).extract(JD)
    assert anns[0].raw_name == "RAG"
    assert anns[0].importance == "must_have"
    assert anns[0].evidence_text == "搭建 RAG 检索链路"


def test_extract_full_returns_soft_requirements(clean_db):
    ext = _extractor(clean_db, GOOD)
    full = ext.extract_full(JD)
    assert full.skills[0].raw_name == "RAG"
    assert full.soft_requirements[0].type == "experience"
    assert full.soft_requirements[0].value == "1-3年"
    assert ext.last_usage["total_tokens"] == 50


def test_markdown_fenced_json_tolerated(clean_db):
    anns = _extractor(clean_db, f"```json\n{GOOD}\n```").extract(JD)
    assert anns[0].raw_name == "RAG"


def test_soft_requirements_optional(clean_db):
    full = _extractor(clean_db, GOOD_SOFTLESS).extract_full(JD)
    assert full.soft_requirements == []


def test_evidence_not_locatable_raises_after_retry(clean_db):
    BAD = GOOD.replace("搭建 RAG 检索链路", "原文不存在的片段")
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [
            {"message": {"content": BAD}}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://t", "k", "m", http=http)
    with pytest.raises(ExtractionFailed, match="重试"):
        LLMSkillExtractor(LLMGateway(clean_db, p, "v1")).extract(JD)
    # 循环 3 次（首次 + 重试 2，ADR-009），但第 3 次的 messages 与第 2 次
    # 完全相同（同 BAD 输出 + 同纠错提示）→ Gateway 缓存命中，provider 实调 2 次
    assert calls["n"] == 2


def test_schema_violation_raises_after_retry(clean_db):
    BAD = '{"skills": [{"raw_name": "RAG"}]}'   # 缺 importance/evidence_text
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = BAD if calls["n"] == 1 else GOOD_SOFTLESS
        return httpx.Response(200, json={"choices": [
            {"message": {"content": body}}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://t", "k", "m", http=http)
    anns = LLMSkillExtractor(LLMGateway(clean_db, p, "v1")).extract(JD)
    assert anns[0].raw_name == "RAG"    # 校验失败 → 重试 → 修正后通过
    assert calls["n"] == 2


def test_retry_message_contains_validation_error(clean_db):
    """重试时把校验错误反馈给模型（对话式修正）。"""
    seen_bodies = []
    BAD = '{"skills": [{"raw_name": "RAG"}]}'

    def handler(req: httpx.Request) -> httpx.Response:
        import json as j
        body = j.loads(req.content)
        seen_bodies.append(body)
        content = BAD if len(seen_bodies) == 1 else GOOD_SOFTLESS
        return httpx.Response(200, json={"choices": [
            {"message": {"content": content}}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://t", "k", "m", http=http)
    LLMSkillExtractor(LLMGateway(clean_db, p, "v1")).extract(JD)
    assert len(seen_bodies[1]["messages"]) == 4   # system+user+assistant+纠错 user
    assert "重新输出" in seen_bodies[1]["messages"][-1]["content"]
