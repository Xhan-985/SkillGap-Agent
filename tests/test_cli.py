import json
import os

from skillgap.cli import build_parser, main
from skillgap.config import settings

TEST_URL = os.environ.get("TEST_DATABASE_URL", settings.test_database_url)


def test_parser_subcommands():
    parser = build_parser()
    for cmd in ["db-upgrade", "seed", "ingest-adzuna", "import", "contribute",
                "delete-contribution", "quality-report", "stats",
                "quarantine-list", "raw-cleanup"]:
        ns = parser.parse_args([cmd] if cmd not in (
            "ingest-adzuna", "import", "contribute", "delete-contribution",
            "stats") else [cmd] + (
            ["--country", "gb", "--query", "LLM"] if cmd == "ingest-adzuna"
            else ["--file", "x.csv"] if cmd == "import"
            else ["--title", "t", "--file", "j.txt", "--consent"]
            if cmd == "contribute"
            else ["--code", "AB12-CD34"] if cmd == "delete-contribution"
            else ["--market", "china"]))
        assert ns.command == cmd


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
