from datetime import datetime, timezone

from skillgap.ingest.pipeline import process_record, run_batch
from skillgap.models import RawRecord, SkillAnnotation, SourceFields

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)

GOOD_JD = ("岗位职责：负责大模型应用开发，搭建 RAG 检索链路与 Agent 编排，"
           "优化 Prompt 与线上推理服务。任职要求：熟悉 LangChain、LangGraph，"
           "精通 Python，了解 Docker 部署。") * 2

SKILLS = [
    SkillAnnotation(raw_name="RAG", importance="must_have", intensity="熟悉",
                    evidence_text="搭建 RAG 检索链路"),
    SkillAnnotation(raw_name="LangChain", importance="must_have", intensity="熟悉",
                    evidence_text="熟悉 LangChain"),
    SkillAnnotation(raw_name="Python", importance="must_have", intensity="精通",
                    evidence_text="精通 Python"),
]


def _rec(**source_over) -> RawRecord:
    src = dict(source_type="dataset_builtin", source_name="demo_dataset",
               collected_at=NOW, source_url=None)
    src.update(source_over)
    return RawRecord(
        title="AI 应用开发工程师", raw_text=GOOD_JD,
        suggested_skills=[
            SkillAnnotation(raw_name="RAG", importance="must_have",
                            intensity="熟悉", evidence_text="搭建 RAG 检索链路"),
            SkillAnnotation(raw_name="Python", importance="must_have",
                            intensity="精通", evidence_text="精通 Python"),
        ],
        source=SourceFields(**src),
    )


def test_insert_active_job_with_skills(clean_db):
    outcome, meta = process_record(clean_db, _rec())
    assert outcome.status == "inserted"
    assert meta.get("market_ambiguous") is not True
    with clean_db.cursor() as cur:
        cur.execute("SELECT * FROM job WHERE id = %s", (outcome.job_id,))
        job = cur.fetchone()
        cur.execute("SELECT count(*) AS c FROM job_skill WHERE job_id = %s",
                    (outcome.job_id,))
        n = cur.fetchone()["c"]
    assert job["market"] == "china"
    assert job["language"] == "zh"
    assert job["status"] == "active"
    assert job["consent_status"] == "none"
    assert n == 2


def test_dedup_same_content_returns_existing(clean_db):
    a, _ = process_record(clean_db, _rec())
    b, _ = process_record(clean_db, _rec())
    assert b.status == "duplicate" and b.job_id == a.job_id
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job")
        assert cur.fetchone()["c"] == 1


def test_quarantine_short_jd_stored_in_raw_jobs(clean_db):
    rec = _rec()
    rec.raw_text = "太短"
    outcome, _ = process_record(clean_db, rec)
    assert outcome.status == "quarantined"
    with clean_db.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM job")
        assert cur.fetchone()["c"] == 0          # 未入库
        cur.execute("SELECT status, error FROM raw_jobs")
        row = cur.fetchone()
    assert row["status"] == "quarantined"
    assert "length" in row["error"]


def test_unresolvable_skill_goes_to_candidates(clean_db):
    rec = _rec()
    rec.suggested_skills = [
        SkillAnnotation(raw_name="某未知新框架", importance="nice_to_have",
                        evidence_text="负责大模型应用开发")]
    outcome, _ = process_record(clean_db, rec)
    assert outcome.status == "inserted"
    with clean_db.cursor() as cur:
        cur.execute("SELECT raw_name, status FROM new_skill_candidate")
        row = cur.fetchone()
    assert row["raw_name"] == "某未知新框架" and row["status"] == "pending"


def test_evidence_not_locatable_marks_extraction_failed(clean_db):
    rec = _rec()
    rec.suggested_skills = [
        SkillAnnotation(raw_name="RAG", importance="must_have",
                        evidence_text="原文不存在的片段")]
    outcome, _ = process_record(clean_db, rec)
    assert outcome.status == "extraction_failed"
    with clean_db.cursor() as cur:
        cur.execute("SELECT status FROM job WHERE id = %s", (outcome.job_id,))
        assert cur.fetchone()["status"] == "extraction_failed"  # 不进统计


def test_user_submitted_pii_redacted_before_insert(clean_db):
    rec = _rec()
    rec.source.source_type = "user_submitted"
    rec.source.source_name = "user_contribution"
    rec.source.consent_status = "market_analysis"
    rec.raw_text = "联系张三 13812345678。" + GOOD_JD
    outcome, _ = process_record(clean_db, rec)
    assert outcome.status == "inserted"
    with clean_db.cursor() as cur:
        cur.execute("SELECT raw_text, parsed_metadata FROM job WHERE id=%s",
                    (outcome.job_id,))
        row = cur.fetchone()
    assert "13812345678" not in row["raw_text"]
    assert "[PHONE_REDACTED]" in row["raw_text"]
    assert row["parsed_metadata"]["pii_redaction"]["hits"]["phone"] == 1


def test_run_batch_report_counts(clean_db):
    records = [_rec(), _rec()]                    # 第二条重复
    bad = _rec(); bad.raw_text = "太短"           # 一条隔离
    records.append(bad)
    report = run_batch(clean_db, records)
    assert report.total == 3
    assert report.inserted == 1
    assert report.duplicates == 1
    assert report.quarantined == 1
    with clean_db.cursor() as cur:
        cur.execute(
            "SELECT total, inserted, duplicates, quarantined FROM ingest_batch")
        row = cur.fetchone()
    assert (row["total"], row["inserted"], row["duplicates"],
            row["quarantined"]) == (3, 1, 1, 1)


def test_batch_idempotent_rerun(clean_db):
    run_batch(clean_db, [_rec()])
    report = run_batch(clean_db, [_rec()])
    assert report.duplicates == 1 and report.inserted == 0
