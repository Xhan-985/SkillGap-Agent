from skillgap.ingest.normalize import (
    canonicalize_for_hash, classify_job_category, content_hash,
    detect_language, determine_market, parse_salary_range,
)


def test_canonicalize_folds_case_width_space():
    a = "熟悉 ＲＡＧ 与　LangChain 编排"
    b = "熟悉 RAG 与 LangChain 编排"
    assert canonicalize_for_hash(a) == canonicalize_for_hash(b)


def test_content_hash_stable_across_formatting():
    a = "岗位：AI工程师。\n要求：熟悉RAG。\n"
    b = "岗位：AI工程师。 要求：熟悉rag。"
    assert content_hash(a) == content_hash(b)


def test_content_hash_differs_for_different_text():
    assert content_hash("熟悉RAG") != content_hash("熟悉vLLM")


def test_detect_language():
    assert detect_language("负责大模型应用开发，熟悉RAG链路") == "zh"
    assert detect_language("We need an LLM engineer with RAG experience") == "en"
    assert detect_language("12345 67890") is None
    # 中文 JD 含英文技能词，主体语言仍是中文（S3 备注）
    assert detect_language("岗位要求：熟悉 RAG、LangChain、Prompt 工程，三年经验") == "zh"


def test_determine_market_by_source_then_language():
    assert determine_market("en", "global") == "global"   # Adzuna 来源权威
    assert determine_market("en", "china") == "china"
    assert determine_market("zh", "both") == "china"
    assert determine_market("en", "both") == "global"
    assert determine_market(None, "both") is None          # 歧义 → 上层标记


def test_parse_salary_range():
    assert parse_salary_range("薪资 15K-25K") == (15000, 25000)
    assert parse_salary_range("15k~25k·14薪") == (15000, 25000)
    assert parse_salary_range("15000-25000 元/月") == (15000, 25000)
    assert parse_salary_range("1.5万-2.5万") == (15000, 25000)
    assert parse_salary_range("面议") == (None, None)


def test_classify_job_category():
    assert classify_job_category("AI 应用开发工程师") == "ai_application_dev"
    assert classify_job_category("Agent 算法工程师") == "agent_dev"
    assert classify_job_category("LLM 全栈工程师") == "llm_fullstack"
    assert classify_job_category("MCP 开发工程师") == "mcp_dev"
    assert classify_job_category("Machine Learning Platform Engineer") == "ai_platform"
    assert classify_job_category("Python 后端开发") == "python_ai_dev"
    assert classify_job_category("Dify 工作流编排师") == "dify_dev"
    assert classify_job_category("运营专员") == "other"
