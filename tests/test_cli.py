import json
import os

import pytest

from skillgap.cli import build_parser, main
from skillgap.config import Settings, settings

TEST_URL = os.environ.get("TEST_DATABASE_URL", settings.test_database_url)


def test_parser_subcommands():
    parser = build_parser()
    for cmd in ["db-upgrade", "seed", "ingest-adzuna", "import", "contribute",
                "delete-contribution", "quality-report", "stats",
                "quarantine-list", "raw-cleanup",
                "jd-analyze", "eval-e1", "backfill-extraction"]:
        ns = parser.parse_args([cmd] if cmd not in (
            "ingest-adzuna", "import", "contribute", "delete-contribution",
            "stats", "jd-analyze") else [cmd] + (
            ["--country", "gb", "--query", "LLM"] if cmd == "ingest-adzuna"
            else ["--file", "x.csv"] if cmd == "import"
            else ["--title", "t", "--file", "j.txt", "--consent"]
            if cmd == "contribute"
            else ["--code", "AB12-CD34"] if cmd == "delete-contribution"
            else ["--market", "china"]
            if cmd == "stats"
            else ["--file", "j.txt", "--title", "t"]))
        assert ns.command == cmd


# ---------- Phase 3：LLM 命令（无 key 路径——不触发真实调用） ----------

@pytest.fixture()
def no_llm_key(monkeypatch):
    monkeypatch.setattr("skillgap.cli.settings", Settings(llm_api_key=""))


def test_jd_analyze_without_key_exits_clean(clean_db, capsys, no_llm_key):
    rc = main(["jd-analyze", "--file", "不存在的文件.txt"], db_url=TEST_URL)
    assert rc == 2
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_eval_e1_without_key_exits_clean_and_no_side_effect(
        clean_db, capsys, no_llm_key):
    rc = main(["eval-e1"], db_url=TEST_URL)
    assert rc == 2
    assert "LLM_API_KEY" in capsys.readouterr().err
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM eval_run")
        assert cur.fetchone()["c"] == 0
        cur.execute("SELECT count(*) AS c FROM evaluation_sample")
        assert cur.fetchone()["c"] == 0   # key 检查先于 seed


def test_backfill_without_key_exits_clean(clean_db, capsys, no_llm_key):
    rc = main(["backfill-extraction"], db_url=TEST_URL)
    assert rc == 2
    assert "LLM_API_KEY" in capsys.readouterr().err


def test_stats_command_outputs_json(clean_db, capsys):
    rc = main(["stats", "--market", "china"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["market"] == "china"


def test_quality_report_command(clean_db, capsys):
    rc = main(["quality-report"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "pii_detection" in out and "missing_field_rate" in out


def test_contribute_without_consent_returns_clean_error(clean_db, tmp_path,
                                                        capsys):
    jd = tmp_path / "jd.txt"
    jd.write_text("岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排。" * 3,
                  encoding="utf-8")
    rc = main(["contribute", "--title", "AI 应用开发工程师", "--file", str(jd)],
              db_url=TEST_URL)
    assert rc == 1
    err = capsys.readouterr().err
    assert "--consent" in err
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job")
        assert cur.fetchone()["c"] == 0   # 未入库
