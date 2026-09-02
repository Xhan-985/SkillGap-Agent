from skillgap.ingest.normalize import (
    JOB_CATEGORIES, canonicalize_for_hash, classify_job_category,
    content_hash, detect_language, determine_market, normalize_job_category,
    parse_salary_range,
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


def test_parse_salary_range_rejects_date():
    # 日期区间不得误判为薪资（真实案例：发布日期 2026-08-25）
    assert parse_salary_range("上海校招生 2026-08-25") == (None, None)
    # 无上下文的大数区间同样拒绝；带上下文才采信
    assert parse_salary_range("薪资范围 20000-35000") == (20000, 35000)
    assert parse_salary_range("编号 20000-35000 仅供参考") == (None, None)


def test_parse_salary_range_rejects_zero_to_one_phrase():
    # "从 0 到 1"式项目描述不得误判为薪资（真实案例：批次 1 抽查发现
    # job 53/72/99 的薪资 0-1000 均来自此短语）
    assert parse_salary_range("有完整应用开发或从 0 到 1 的项目实践") == (None, None)
    assert parse_salary_range("有从 0 到 1 完成项目并持续迭代的经历") == (None, None)
    assert parse_salary_range("了解并参与 AI Agent 从0到1的过程") == (None, None)
    # 正向对照：无单位小数值区间仍按 K 采信
    assert parse_salary_range("综合薪资 12 - 25") == (12000, 25000)


def test_classify_job_category():
    assert classify_job_category("AI 应用开发工程师") == "ai_application_dev"
    assert classify_job_category("Agent 算法工程师") == "agent_dev"
    assert classify_job_category("LLM 全栈工程师") == "llm_fullstack"
    assert classify_job_category("MCP 开发工程师") == "mcp_dev"
    assert classify_job_category("Machine Learning Platform Engineer") == "ai_platform"
    assert classify_job_category("Python 后端开发") == "python_ai_dev"
    assert classify_job_category("Dify 工作流编排师") == "dify_dev"
    assert classify_job_category("运营专员") == "other"


def test_classify_job_category_title_takes_priority():
    # 真实案例：标题是 Agent 岗，正文前 500 字出现"AI产品"——标题优先
    assert classify_job_category(
        "Agent开发工程师（2027届秋招）",
        "参与Agent应用工程开发，完成AI产品的上线;参与Agent基础开发框架。"
    ) == "agent_dev"
    # 标题无信号时仍回落到正文
    assert classify_job_category(
        "软件工程师", "负责 Dify 工作流编排与平台建设") == "dify_dev"


def test_normalize_job_category_valid_passthrough():
    assert (normalize_job_category("agent_dev", "任意标题")
            == "agent_dev")
    assert normalize_job_category(None, "Agent开发工程师") == "agent_dev"


def test_normalize_job_category_free_text_falls_back():
    # 真实案例：采集批次中的自由文本类别 → 按关键词回退归类
    assert normalize_job_category(
        "AI全栈", "AI全栈工程师 - 飞书项目") == "llm_fullstack"
    assert normalize_job_category(
        "Agent研发", "资深Agent研发工程师") == "agent_dev"
    assert normalize_job_category(
        "AI应用", "AI应用工程师 应届生") == "ai_application_dev"
    assert normalize_job_category(
        "AI Infra", "AI Infra工程师") == "ai_platform"
    # 无任何关键词命中 → other（合法枚举，不再触发 CHECK 约束）
    assert normalize_job_category(
        "AI Native", "AI-Native 开发工程师") in JOB_CATEGORIES
