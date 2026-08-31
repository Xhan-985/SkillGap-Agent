"""交互式收集器（collector）纯函数层测试。

交互 I/O 薄壳不测（smoke 覆盖）；字段推断/CSV 写入/回读走这里。
"""
from pathlib import Path

from skillgap.ingest.collector import (
    append_row, build_row, load_alias_table, prepare_text, suggest_skills,
)
from skillgap.ingest.importer import parse_file

JD = ("岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排，"
      "精通 Python，熟悉 LangChain，了解 Docker 部署。")


def test_alias_table_loaded_and_sorted():
    table = load_alias_table()
    assert ("RAG", "RAG") in table
    assert any(c == "Python" and a == "py" for a, c in table)
    lens = [len(a) for a, _ in table]
    assert lens == sorted(lens, reverse=True)   # 长 alias 优先匹配


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
