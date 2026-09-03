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
                "jd-analyze", "eval-e1", "backfill-extraction",
                "snapshot-create", "skill-evidence", "market-crosscheck",
                "resume-analyze", "profile-get", "profile-add-skill",
                "candidate-delete", "gap-get"]:
        ns = parser.parse_args([cmd] if cmd not in (
            "ingest-adzuna", "import", "contribute", "delete-contribution",
            "stats", "jd-analyze", "skill-evidence",
            "resume-analyze", "profile-get", "profile-add-skill",
            "candidate-delete", "gap-get") else [cmd] + (
            ["--country", "gb", "--query", "LLM"] if cmd == "ingest-adzuna"
            else ["--file", "x.csv"] if cmd == "import"
            else ["--title", "t", "--file", "j.txt", "--consent"]
            if cmd == "contribute"
            else ["--code", "AB12-CD34"] if cmd == "delete-contribution"
            else ["--market", "china"]
            if cmd == "stats"
            else ["--skill", "RAG"]
            if cmd == "skill-evidence"
            else ["--file", "j.txt", "--title", "t"]
            if cmd == "jd-analyze"
            else ["--file", "r.txt"]
            if cmd == "resume-analyze"
            else ["--candidate-id", "1", "--skill", "RAG", "--level", "4"]
            if cmd == "profile-add-skill"
            else ["--candidate-id", "1"]))
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


def test_eval_e1_without_taxonomy_exits_with_hint(
        clean_db, capsys, monkeypatch):
    """fresh DB 漏跑 seed：词表为空时给出明确提示，不产出误导性 block 报告。"""
    from skillgap.taxonomy.seed import seed_all

    monkeypatch.setattr("skillgap.cli.settings", Settings(llm_api_key="k"))
    with clean_db.cursor() as cur:
        cur.execute("TRUNCATE skill, skill_alias RESTART IDENTITY CASCADE")
    clean_db.commit()
    try:
        rc = main(["eval-e1"], db_url=TEST_URL)
        assert rc == 2
        assert "seed" in capsys.readouterr().err
        with clean_db.cursor() as cur:
            cur.execute("SELECT count(*) AS c FROM eval_run")
            assert cur.fetchone()["c"] == 0
            cur.execute("SELECT count(*) AS c FROM evaluation_sample")
            assert cur.fetchone()["c"] == 0
    finally:
        seed_all(clean_db)          # 恢复后续测试所需的词表


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


# ---------- Phase 4：stats 切片 + snapshot-create / skill-evidence / market-crosscheck ----------


def test_stats_slice_flags(clean_db, capsys):
    from tests.test_stats import _jobs
    _jobs(clean_db, 35, city="北京", job_category="agent_dev")
    rc = main(["stats", "--market", "china", "--category", "agent_dev",
               "--city", "北京", "--min-sample", "5"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["filters"]["category"] == "agent_dev"
    assert out["filters"]["city"] == "北京"
    assert out["sample_size"] == 35


def test_snapshot_create_command(clean_db, capsys):
    from tests.test_stats import _jobs
    _jobs(clean_db, 35)
    rc = main(["snapshot-create", "--market", "china"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok" and "snapshot#" in out["evidence_ref"]


def test_skill_evidence_command(clean_db, capsys):
    from tests.test_stats import _jobs
    _jobs(clean_db, 35)
    rc = main(["skill-evidence", "--market", "china", "--skill", "RAG"],
              db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skill_id"] == "RAG"
    assert out["jd_count"] == 35


def test_market_crosscheck_command(clean_db, capsys):
    from tests.test_stats import _jobs
    _jobs(clean_db, 35)
    rc = main(["market-crosscheck", "--market", "china"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok" and "tau" in out


# ---------- Phase 5：Candidate Profile 命令 ----------

def test_resume_analyze_without_key_exits_clean(clean_db, capsys, no_llm_key):
    rc = main(["resume-analyze", "--file", "不存在的文件.txt"], db_url=TEST_URL)
    assert rc == 2
    assert "LLM_API_KEY" in capsys.readouterr().err


def _make_candidate(clean_db):
    from skillgap.profile.service import analyze_resume
    from tests.profile_fixtures import (
        EXTRACTION_A, FakeResumeExtractor, RESUME_A,
    )
    out = analyze_resume(clean_db, RESUME_A, FakeResumeExtractor(EXTRACTION_A))
    return out["candidate_id"]


def test_profile_get_command(clean_db, capsys):
    cid = _make_candidate(clean_db)
    rc = main(["profile-get", "--candidate-id", str(cid)], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert {s["skill_id"] for s in out["skills"]} == {"RAG", "Python"}
    assert out["soft_profile"]["experience_years"]["value"] == 2


def test_profile_get_not_found_returns_1(clean_db, capsys):
    rc = main(["profile-get", "--candidate-id", "42"], db_url=TEST_URL)
    assert rc == 1
    assert "错误" in capsys.readouterr().err


def test_profile_add_skill_command(clean_db, capsys):
    cid = _make_candidate(clean_db)
    rc = main(["profile-add-skill", "--candidate-id", str(cid),
               "--skill", "Docker", "--level", "3"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["skill_id"] == "Docker"
    assert out["confidence"] == 1.0
    assert out["source_type"] == "manual"


def test_profile_add_skill_unknown_returns_1(clean_db, capsys):
    cid = _make_candidate(clean_db)
    rc = main(["profile-add-skill", "--candidate-id", str(cid),
               "--skill", "量子编程", "--level", "3"], db_url=TEST_URL)
    assert rc == 1
    assert "词表" in capsys.readouterr().err


def test_candidate_delete_command(clean_db, capsys):
    cid = _make_candidate(clean_db)
    rc = main(["candidate-delete", "--candidate-id", str(cid)], db_url=TEST_URL)
    assert rc == 0
    assert "204 deleted" in capsys.readouterr().out
    rc = main(["candidate-delete", "--candidate-id", str(cid)], db_url=TEST_URL)
    assert rc == 1
    assert "404" in capsys.readouterr().out


# ---------- Phase 6：Skill Gap 命令 ----------

def _mk_gap_fixture(clean_db, n_jobs=1):
    """画像 B（RAG 0.3 / MCP 0.3）+ 1 条要求 Docker 熟练的岗位。"""
    from tests.profile_fixtures import (
        EXTRACTION_B, FakeResumeExtractor, RESUME_B,
    )
    from skillgap.profile.service import analyze_resume
    from tests.test_schema import _insert_job, _job_kwargs, _source
    cid = analyze_resume(clean_db, RESUME_B,
                         FakeResumeExtractor(EXTRACTION_B))["candidate_id"]
    sid = _source(clean_db)
    jid = _insert_job(clean_db, **_job_kwargs(sid, content_hash="h-cli-gap"))
    skill_id = clean_db.execute(
        "SELECT id FROM skill WHERE canonical_name = 'Docker'"
    ).fetchone()["id"]
    clean_db.execute(
        """INSERT INTO job_skill
           (job_id, skill_id, importance, intensity, evidence_text,
            extracted_by) VALUES (%s, %s, 'must_have', '熟练', '要求 Docker',
            'manual')""", (jid, skill_id))
    clean_db.commit()
    return cid, jid


def test_gap_get_job_mode_command(clean_db, capsys):
    cid, jid = _mk_gap_fixture(clean_db)
    rc = main(["gap-get", "--candidate-id", str(cid), "--job-id", str(jid)],
              db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "job"
    assert [g["skill_id"] for g in out["gaps"]] == ["Docker"]
    assert out["gaps"][0]["gap"] == 4


def test_gap_get_category_mode_command(clean_db, capsys):
    """单岗类目：Docker freq 1.0 ≥ 0.2 入清单 → 画像 B 无 Docker → gap 4。"""
    cid, _ = _mk_gap_fixture(clean_db)
    rc = main(["gap-get", "--candidate-id", str(cid),
               "--category", "ai_application_dev"], db_url=TEST_URL)
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["mode"] == "category"
    assert [g["skill_id"] for g in out["gaps"]] == ["Docker"]
    assert out["gaps"][0]["gap"] == 4
    assert out["gaps"][0]["demand"]["frequency"] == 1.0


def test_gap_get_not_found_returns_1(clean_db, capsys):
    cid, _ = _mk_gap_fixture(clean_db)
    rc = main(["gap-get", "--candidate-id", str(cid), "--job-id", "999"],
              db_url=TEST_URL)
    assert rc == 1
    assert "错误" in capsys.readouterr().err


def test_gap_get_mutually_exclusive_returns_2(clean_db, capsys):
    cid, jid = _mk_gap_fixture(clean_db)
    rc = main(["gap-get", "--candidate-id", str(cid), "--job-id", str(jid),
               "--category", "ai_application_dev"], db_url=TEST_URL)
    assert rc == 2
    assert "二选一" in capsys.readouterr().err
