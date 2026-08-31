import json

import pytest

from skillgap.ingest.importer import REQUIRED_COLUMNS, parse_file

CSV_CONTENT = """title,company,city,country,region,salary_min,salary_max,salary_currency,job_category,raw_text,soft_requirements,skills,source_type,source_name,source_url,collected_at,submitted_at,consent_status,data_quality
AI 应用开发工程师,某科技,北京,中国,华北,15000,25000,CNY,,{jd},,"[{""raw_name"":""RAG"",""importance"":""must_have"",""intensity"":""熟悉"",""evidence_text"":""搭建 RAG 检索链路""}]",public_job_page,company_career_page,https://example.com/j/1,2026-08-31,,,auto_passed
Agent 工程师,,,,,,,CNY,,{jd},,"[{""raw_name"":""LangGraph"",""importance"":""must_have"",""evidence_text"":""Agent 编排""}]",public_job_page,company_career_page,https://example.com/j/2,2026-08-31,,,auto_passed
""".replace("{jd}", "岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。")


def _write(tmp_path, content, name, encoding="utf-8"):
    p = tmp_path / name
    p.write_text(content, encoding=encoding)
    return str(p)


def test_parse_csv_ok(tmp_path):
    path = _write(tmp_path, CSV_CONTENT, "jobs.csv")
    records = parse_file(path)
    assert len(records) == 2
    assert records[0].source.source_type == "public_job_page"
    assert records[0].source.source_url == "https://example.com/j/1"
    assert records[0].suggested_skills[0].raw_name == "RAG"
    assert records[0].salary_max == 25000
    assert records[1].job_category == "" or records[1].job_category is None


def test_parse_json_ok(tmp_path):
    data = [{
        "title": "AI 应用开发工程师",
        "raw_text": "岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。",
        "city": "北京",
        "skills": [{"raw_name": "RAG", "importance": "must_have",
                    "evidence_text": "搭建 RAG 检索链路"}],
        "source_type": "dataset_builtin", "source_name": "demo_dataset",
        "collected_at": "2026-08-31T00:00:00Z",
    }]
    path = _write(tmp_path, json.dumps(data, ensure_ascii=False), "jobs.json")
    records = parse_file(path)
    assert len(records) == 1
    assert records[0].source.source_name == "demo_dataset"


def test_missing_required_columns_rejected(tmp_path):
    path = _write(tmp_path, "title,raw_text\nx,y", "bad.csv")
    with pytest.raises(ValueError) as e:
        parse_file(path)
    assert "缺少" in str(e.value)


def test_row_level_error_does_not_abort(tmp_path):
    rows = [
        {"title": "AI 工程师",
         "raw_text": "岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。",
         "source_type": "dataset_builtin", "source_name": "demo_dataset",
         "collected_at": "2026-08-31T00:00:00Z"},
        {"title": "坏行", "raw_text": "缺 source",
         "source_type": "dataset_builtin", "source_name": "demo_dataset"},
    ]
    path = _write(tmp_path, json.dumps(rows), "mixed.json")
    with pytest.warns(UserWarning):
        records = parse_file(path)
    assert len(records) == 1


def test_utf8_bom_tolerated(tmp_path):
    path = _write(tmp_path, "\ufeff" + CSV_CONTENT, "bom.csv")
    assert len(parse_file(path)) == 2
