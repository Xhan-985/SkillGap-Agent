"""Phase 5 LLMResumeExtractor 单测（httpx.MockTransport，零真实 LLM）。"""
import httpx
import pytest

from skillgap.extract.llm_extractor import ExtractionFailed
from skillgap.llm.gateway import LLMGateway
from skillgap.llm.provider import OpenAICompatibleProvider
from skillgap.profile.extractor import LLMResumeExtractor
from skillgap.profile.prompt import RESUME_PROMPT_VERSION

RESUME = (
    "两年后端开发经验。\n"
    "项目：电商搜索系统，用 pgvector+Hybrid Search+RRF+Rerank 搭建检索链路，召回率提升 18%。\n"
    "参与公司知识库项目。\n"
    "熟悉 RAG。本科，软件工程专业。\n"
)

GOOD = """{"skills": [
 {"raw_name": "RAG", "level": 4, "evidences": [
   {"type": "project_detail", "text": "pgvector+Hybrid Search+RRF+Rerank 搭建检索链路"}]},
 {"raw_name": "Docker", "level": 3, "evidences": [
   {"type": "bare_claim", "text": "熟悉 RAG"}]}],
 "soft_profile": {"experience_years": {"value": 2, "evidence_text": "两年后端开发经验"},
  "education": {"value": "本科·软件工程", "evidence_text": "本科，软件工程专业"},
  "languages": null}}"""


def _extractor(clean_db, content: str | None = None, responses=None):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = (responses[calls["n"] - 1] if responses is not None
                else content)
        return httpx.Response(200, json={"choices": [
            {"message": {"content": body}}],
            "usage": {"total_tokens": 50}, "model": "m"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://t", "k", "m", http=http)
    return (LLMResumeExtractor(LLMGateway(clean_db, provider=p,
                                          prompt_version=RESUME_PROMPT_VERSION)),
            calls)


def test_extract_ok_with_soft_profile(clean_db):
    ext, _ = _extractor(clean_db, GOOD)
    result = ext.extract_full(RESUME)
    assert result.skills[0].raw_name == "RAG"
    assert result.skills[0].level == 4
    assert result.skills[0].evidences[0].type == "project_detail"
    assert result.soft_profile.experience_years.value == 2
    assert result.soft_profile.education.value == "本科·软件工程"
    assert result.soft_profile.languages is None
    assert ext.last_usage["total_tokens"] == 50


def test_markdown_fenced_json_tolerated(clean_db):
    ext, _ = _extractor(clean_db, f"```json\n{GOOD}\n```")
    assert ext.extract_full(RESUME).skills[0].raw_name == "RAG"


def test_level_out_of_range_raises_then_recovers(clean_db):
    BAD = GOOD.replace('"level": 4', '"level": 6')
    ext, _ = _extractor(clean_db, responses=[BAD, GOOD])
    assert ext.extract_full(RESUME).skills[0].level == 4


def test_invalid_evidence_type_raises_then_recovers(clean_db):
    BAD = GOOD.replace('"project_detail"', '"hearsay"')
    ext, _ = _extractor(clean_db, responses=[BAD, GOOD])
    assert ext.extract_full(RESUME).skills[0].evidences[0].type == "project_detail"


def test_evidence_not_locatable_raises_after_retry(clean_db):
    BAD = GOOD.replace("熟悉 RAG", "原文不存在的片段")
    ext, calls = _extractor(clean_db, responses=[BAD, BAD, BAD])
    with pytest.raises(ExtractionFailed, match="重试"):
        ext.extract_full(RESUME)
    # 首次 + 重试 2 → 但第 3 次 messages 与第 2 次相同 → 缓存命中（同 JD 抽取器）
    assert calls["n"] == 2


def test_retry_message_contains_validation_error(clean_db):
    BAD = '{"skills": [{"raw_name": "RAG"}]}'   # 缺 level/evidences
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json as j
        seen.append(j.loads(req.content))
        body = BAD if len(seen) == 1 else GOOD
        return httpx.Response(200, json={"choices": [
            {"message": {"content": body}}]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAICompatibleProvider("https://t", "k", "m", http=http)
    LLMResumeExtractor(LLMGateway(clean_db, p, "v1")).extract_full(RESUME)
    assert len(seen[1]["messages"]) == 4   # system+user+assistant+纠错 user
    assert "重新输出" in seen[1]["messages"][-1]["content"]


def test_soft_profile_all_null_tolerated(clean_db):
    BODY = ('{"skills": [{"raw_name": "RAG", "level": 3, "evidences": '
            '[{"type": "bare_claim", "text": "熟悉 RAG"}]}], '
            '"soft_profile": {"experience_years": null, '
            '"education": null, "languages": null}}')
    ext, _ = _extractor(clean_db, BODY)
    result = ext.extract_full(RESUME)
    assert result.soft_profile.experience_years is None
    assert result.soft_profile.education is None


def test_soft_profile_evidence_not_locatable(clean_db):
    BAD = GOOD.replace("两年后端开发经验", "五年前端开发经验")
    ext, _ = _extractor(clean_db, responses=[BAD, GOOD])
    result = ext.extract_full(RESUME)
    assert result.soft_profile.experience_years.value == 2
