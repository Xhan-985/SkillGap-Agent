"""交互式收集器（collector）纯函数层测试。

交互 I/O 薄壳不测（smoke 覆盖）；字段推断/CSV 写入/回读走这里。
"""
from pathlib import Path

from skillgap.ingest.collector import (
    append_row, build_row, detect_city, detect_company, extract_title,
    load_alias_table, prepare_text, suggest_skills,
)
from skillgap.ingest.importer import parse_file

JD = ("岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排，"
      "精通 Python，熟悉 LangChain，了解 Docker 部署。")


# ---------- 粘贴优先：字段自动识别 ----------

def test_extract_title_from_headline_line():
    text = "AI 应用开发工程师\n岗位职责：负责大模型应用开发。\n任职要求：精通 Python。"
    assert extract_title(text) == "AI 应用开发工程师"


def test_extract_title_strips_recruit_prefix():
    text = "招聘岗位：LLM 平台工程师\n岗位职责：负责推理服务。"
    assert extract_title(text) == "LLM 平台工程师"


def test_extract_title_from_company_recruit_sentence():
    text = "某科技公司诚聘资深算法工程师，负责大模型应用开发。"
    assert extract_title(text) == "资深算法工程师"


def test_extract_title_english():
    text = "Senior LLM Engineer\nResponsibilities: Build RAG pipelines."
    assert extract_title(text) == "Senior LLM Engineer"


def test_extract_title_skips_responsibility_lines():
    # 首行是 JD 套话时不应误当标题；从后续行找岗位信号
    text = "岗位职责：负责大模型应用开发，搭建 RAG 链路。\n岗位名称：AI 工程师"
    assert extract_title(text) == "AI 工程师"


def test_extract_title_none_when_no_signal():
    assert extract_title("这是一段没有任何岗位信号的文字。") is None


def test_detect_company():
    text = "关于我们：北京某科技有限公司致力于 AI 应用。\n岗位职责：负责开发。"
    assert detect_company(text) == "北京某科技有限公司"


def test_detect_company_none():
    assert detect_company(JD) is None


def test_detect_city():
    assert detect_city("工作地点：上海浦东\n岗位职责：开发。") == "上海"
    assert detect_city("Base 杭州，负责大模型应用开发。") == "杭州"


def test_detect_city_none():
    assert detect_city(JD) is None


def test_alias_table_loaded_and_sorted():
    table = load_alias_table()
    assert ("RAG", "RAG") in table
    assert any(c == "Python" and a == "py" for a, c in table)
    lens = [len(a) for a, _ in table]
    assert lens == sorted(lens, reverse=True)   # 长 alias 优先匹配


def test_alias_table_has_no_generic_aliases():
    """通用技术词不得挂任何具体产品（否则"向量数据库"被硬归 Milvus）。"""
    table = load_alias_table()
    names = {a for a, _ in table}
    assert "向量数据库" not in names
    assert "图数据库" not in names


def test_suggest_skills_infers_from_capability_words():
    """措辞推断：不写具体技术名也能给出建议（标 inferred，evidence=措辞原文）。"""
    table = load_alias_table()
    text = "负责企业知识库问答系统的建设与优化，熟悉容器化部署。"
    by_name = {s.canonical: s for s in suggest_skills(text, table)}
    rag = by_name["RAG"]
    assert rag.inferred is True
    assert rag.evidence_text == "知识库问答"        # 证据=可定位的措辞原文
    assert by_name["Docker"].inferred is True
    assert by_name["Docker"].evidence_text == "容器化"


def test_suggest_skills_inferred_prompt():
    text = "Optimize prompt quality for LLM applications."
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    assert by_name["Prompt Engineering"].evidence_text == "prompt"


def test_suggest_skills_inferred_not_duplicated_with_alias():
    # 同一技能已被 alias 命中时，推断层不再重复给出
    text = "搭建 RAG 检索链路与知识库问答系统。"
    rags = [s for s in suggest_skills(text, load_alias_table())
            if s.canonical == "RAG"]
    assert len(rags) == 1
    assert rags[0].inferred is False


def test_suggest_skills_evidence_is_original_text():
    suggs = suggest_skills(JD, load_alias_table())
    by_name = {s.canonical: s for s in suggs}
    assert {"RAG", "Python", "Docker", "LangChain"} <= set(by_name)
    for s in suggs:
        assert s.evidence_text in JD            # 证据=原文片段（可定位）


def test_suggest_intensity_from_preceding_word():
    by_name = {s.canonical: s for s in suggest_skills(JD, load_alias_table())}
    assert by_name["Python"].intensity == "精通"
    assert by_name["Docker"].intensity == "了解"


# ---------- importance 自动判定（加分项章节/措辞） ----------

def test_importance_nice_when_in_bonus_section():
    text = ("任职要求：\n1. 精通 Python；\n2. 熟悉 FastAPI。\n"
            "加分项：\n1. 了解 Kubernetes；\n2. 有 Cursor 使用经验。")
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    assert by_name["Python"].importance_hint == "must_have"
    assert by_name["Kubernetes"].importance_hint == "nice_to_have"


def test_importance_hard_section_after_bonus_wins():
    text = ("加分项：\n1. 了解 Milvus。\n"
            "任职要求：\n1. 精通 Docker。")
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    assert by_name["Milvus"].importance_hint == "nice_to_have"
    assert by_name["Docker"].importance_hint == "must_have"


def test_importance_intensity_word_leaning_nice():
    # 不在加分章节，但"了解"级技能倾向 nice_to_have
    by_name = {s.canonical: s for s in suggest_skills(JD, load_alias_table())}
    assert by_name["Docker"].importance_hint == "nice_to_have"
    assert by_name["Python"].importance_hint == "must_have"


def test_importance_nice_words_in_sentence():
    text = "熟悉 Redis，有 LangChain 经验者优先。"
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    assert by_name["LangChain"].importance_hint == "nice_to_have"
    assert by_name["Redis"].importance_hint == "must_have"


# ---------- 择一逻辑（至少一门 / 或） ----------

def test_alternation_at_least_one():
    # "Go/Python/C++ 至少一门"——择一组内每个都是 nice_to_have（无单独必需）
    text = "任职要求：熟练掌握 Go/Python/C++ 至少一门编程语言。"
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    for name in ("Go", "Python", "C++"):
        assert by_name[name].importance_hint == "nice_to_have", name


def test_alternation_or_separator():
    text = "熟悉 LangChain 或 LlamaIndex 框架。"
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    assert by_name["LangChain"].importance_hint == "nice_to_have"
    assert by_name["LlamaIndex"].importance_hint == "nice_to_have"


def test_conjunctive_list_stays_must():
    # 顿号/逗号=并列（都要），不触发择一
    text = "精通 Python、Docker，熟悉 Kubernetes。"
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    assert by_name["Python"].importance_hint == "must_have"
    assert by_name["Docker"].importance_hint == "must_have"
    assert by_name["Kubernetes"].importance_hint == "must_have"


def test_alternation_not_leak_across_clause():
    text = "精通 Go、Python 至少一门；熟悉 Docker。"
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    assert by_name["Go"].importance_hint == "nice_to_have"
    assert by_name["Docker"].importance_hint == "must_have"


def test_at_least_one_year_not_alternation():
    # "至少一年工作经验"不是技能择一，不得误降级
    text = "至少一年工作经验，熟悉 Docker。"
    by_name = {s.canonical: s for s in suggest_skills(text, load_alias_table())}
    assert by_name["Docker"].importance_hint == "must_have"


def test_java_not_matched_inside_javascript():
    text = "熟悉 JavaScript 与 TypeScript。"
    names = {s.canonical for s in suggest_skills(text, load_alias_table())}
    assert "Java" not in names
    assert {"JavaScript", "TypeScript"} <= names


def test_short_ascii_alias_requires_word_boundary():
    text = "我们使用 Python，团队氛围 happy"
    assert "Python" in {s.canonical for s in suggest_skills(text, load_alias_table())}
    text2 = "团队 happy 一起工作"
    assert "Python" not in {s.canonical for s in suggest_skills(text2, load_alias_table())}


def test_prepare_text_redacts_phone():
    text = JD + " 联系电话：13800138000"
    out, report = prepare_text(text)
    assert "[PHONE_REDACTED]" in out
    assert report["hits"]["phone"] >= 1


def test_append_row_creates_zh_header_with_bom(tmp_path):
    p = tmp_path / "batch_1.csv"
    row = build_row(
        title="AI 应用开发工程师", raw_text=JD, company="某科技", city="北京",
        source_url="https://example.com/j/1",
        skills=[{"raw_name": "RAG", "importance": "must_have",
                 "intensity": "熟悉", "evidence_text": "搭建 RAG 检索链路"}])
    append_row(p, row)
    append_row(p, row)                     # 追加：不得在文件中部再写 BOM
    data = p.read_bytes()
    assert data[:3] == b"\xef\xbb\xbf"     # 文件头 BOM（Excel 识别）
    assert data.count(b"\xef\xbb\xbf") == 1
    header_line = data.decode("utf-8-sig").splitlines()[0]
    assert header_line.split(",")[0] == "岗位名称"


def test_append_row_roundtrip_via_parse_file(tmp_path):
    """写入的 CSV 能被导入器原样解析（模板契约闭环）。"""
    p = tmp_path / "batch_1.csv"
    row = build_row(
        title="AI 应用开发工程师", raw_text=JD, company="某科技", city="北京",
        salary_min=15000, salary_max=25000, salary_currency="CNY",
        source_url="https://example.com/j/1",
        skills=[{"raw_name": "RAG", "importance": "must_have",
                 "intensity": "熟悉", "evidence_text": "搭建 RAG 检索链路"}])
    append_row(p, row)
    records = parse_file(p)
    assert len(records) == 1
    r = records[0]
    assert r.title == "AI 应用开发工程师"
    assert r.company_name == "某科技"
    assert r.city == "北京"
    assert r.salary_min == 15000 and r.salary_max == 25000
    assert r.source.source_type == "public_job_page"
    assert r.source.source_name == "company_career_page"
    assert r.source.source_url == "https://example.com/j/1"
    assert r.source.consent_status == "none"
    assert r.source.data_quality == "human_reviewed"
    assert r.suggested_skills[0].raw_name == "RAG"
    assert r.suggested_skills[0].importance == "must_have"
    assert r.suggested_skills[0].evidence_text == "搭建 RAG 检索链路"
