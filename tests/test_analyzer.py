import httpx
import pytest

from skillgap.extract.analyzer import JDValidationError, analyze_jd, backfill_pending
from skillgap.extract.llm_extractor import LLMSkillExtractor
from skillgap.llm.gateway import LLMGateway
from skillgap.llm.provider import OpenAICompatibleProvider
from tests.test_llm_extractor import GOOD

JD = ("岗位职责：搭建 RAG 检索链路与 Agent 编排，优化 Prompt 工程。"
      "要求：1-3年大模型应用开发经验，精通 Python，熟悉 LangChain。") * 2

LLM_OK = {"choices": [{"message": {"content": GOOD}}],
          "usage": {"total_tokens": 88}, "model": "deepseek-chat"}


def _analyze(clean_db, content=GOOD):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [
            {"message": {"content": content}}],
            "usage": {"total_tokens": 88}, "model": "deepseek-chat"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    gw = LLMGateway(clean_db,
                    OpenAICompatibleProvider("https://t", "k", "deepseek-chat",
                                             http=http), "v1")
    extractor = LLMSkillExtractor(gw)
    return lambda jd: analyze_jd(clean_db, jd, extractor=extractor)


def test_analyze_jd_structure(clean_db):
    out = _analyze(clean_db)(JD)
    assert out["job"]["language"] == "zh"
    assert out["job"]["market"] == "china"
    assert out["job"]["job_category"] == "ai_application_dev"
    assert out["core_skills"][0]["raw_name"] == "RAG"
    assert out["core_skills"][0]["evidence_text"]
    assert out["secondary_skills"] == []        # GOOD 无 nice_to_have
    assert out["soft_requirements"][0]["type"] == "experience"
    assert out["extraction_meta"]["prompt_version"] == "v1"
    assert out["extraction_meta"]["model"] == "deepseek-chat"
    assert out["extraction_meta"]["latency_ms"] >= 0
    assert out["extraction_meta"]["total_tokens"] == 88


def test_analyze_jd_english_market_global(clean_db):
    en_jd = ("We are hiring an AI engineer to build RAG pipelines and Agent "
             "orchestration, optimize prompt engineering. 3+ years LLM app "
             "experience, proficient in Python, familiar with LangChain.") * 2
    EN_GOOD = ('{"skills": [{"raw_name": "RAG", "importance": "must_have", '
               '"evidence_text": "build RAG pipelines"}], '
               '"soft_requirements": [{"type": "experience", "value": "3+ years", '
               '"evidence_text": "3+ years LLM app experience"}]}')
    out = _analyze(clean_db, EN_GOOD)(en_jd)
    assert out["job"]["language"] == "en"
    assert out["job"]["market"] == "global"


def test_short_jd_raises_validation(clean_db):
    with pytest.raises(JDValidationError, match="50"):
        _analyze(clean_db)("太短")


def test_too_long_jd_raises_validation(clean_db):
    with pytest.raises(JDValidationError, match="20000"):
        _analyze(clean_db)("x" * 20001)


def test_no_skill_jd_reports_empty_not_silent(clean_db):
    EMPTY = '{"skills": [], "soft_requirements": []}'
    out = _analyze(clean_db, EMPTY)(
        "岗位职责：负责部门日常事务管理与跨团队沟通协调，组织会议与文档归档，"
        "支持业务团队的行政需求并跟踪落地情况，定期汇报进展。")
    assert out["core_skills"] == [] and out["secondary_skills"] == []
    assert out["extraction_meta"]["skill_count"] == 0   # 明示而非静默


def test_backfill_pending_jobs(clean_db):
    """Phase 2 移交：user_submitted 贡献无标注 → extraction_status=pending；
    回填后 job_skill 入库（extracted_by='llm'）、pending 标记清除。"""
    from skillgap.ingest.contribute import contribute_jd
    from skillgap.taxonomy.seed import seed_all
    seed_all(clean_db)
    r = contribute_jd(clean_db, JD, True, "AI 应用开发工程师")
    with clean_db.cursor() as cur:
        cur.execute("SELECT parsed_metadata->>'extraction_status' AS s "
                    "FROM job WHERE id=%s", (r.job_id,))
        assert cur.fetchone()["s"] == "pending"   # 前置：确实处于 pending

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=LLM_OK)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    gw = LLMGateway(clean_db,
                    OpenAICompatibleProvider("https://t", "k", "deepseek-chat",
                                             http=http), "v1")
    n = backfill_pending(clean_db, LLMSkillExtractor(gw))
    assert n == 1
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c, max(extracted_by) AS by "
                    "FROM job_skill WHERE job_id=%s", (r.job_id,))
        row = cur.fetchone()
        cur.execute("SELECT parsed_metadata->'extraction_status' AS s "
                    "FROM job WHERE id=%s", (r.job_id,))
        after = cur.fetchone()["s"]
    assert row["c"] >= 1 and row["by"] == "llm"
    assert after is None                        # pending 标记已清除


def test_backfill_no_pending_is_noop(clean_db):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=LLM_OK)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    gw = LLMGateway(clean_db,
                    OpenAICompatibleProvider("https://t", "k", "m", http=http),
                    "v1")
    assert backfill_pending(clean_db, LLMSkillExtractor(gw)) == 0
