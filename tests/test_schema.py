"""Schema 约束测试：九字段/唯一/CHECK（DATA_MODEL §3 + 评审 B1）。"""
from datetime import datetime, timezone

import psycopg
import pytest

from skillgap.ingest.sources import DATA_SOURCES

NOW = datetime(2026, 8, 31, 12, 0, tzinfo=timezone.utc)


def _source(clean_db, **over):
    row = dict(DATA_SOURCES[1])  # company_career_page（both 市场）
    row.update(over)
    with clean_db.cursor() as cur:
        # db_conn 已 seed 五来源：同名来源幂等取回 id，新名（如 u1）插入
        cur.execute(
            """INSERT INTO data_source (source_type, source_name, trust_tier,
               license_or_usage_note, covers_market, terms_checked_at)
               VALUES (%(source_type)s, %(source_name)s, %(trust_tier)s,
               %(license_or_usage_note)s, %(covers_market)s, %(terms_checked_at)s)
               ON CONFLICT (source_name) DO UPDATE SET
                 covers_market = EXCLUDED.covers_market
               RETURNING id""",
            row,
        )
        sid = cur.fetchone()["id"]
    clean_db.commit()
    return sid


def _job_kwargs(source_id, **over):
    kw = dict(
        title="AI 应用开发工程师", job_category="ai_application_dev",
        market="china", language="zh", raw_text="x" * 100, status="active",
        source_id=source_id, source_type="public_job_page",
        source_url="https://example.com/job/1", collected_at=NOW,
        content_hash="h1", data_quality="auto_passed",
    )
    kw.update(over)
    return kw


def _insert_job(clean_db, **kw):
    cols = ", ".join(kw.keys())
    phs = ", ".join(f"%({k})s" for k in kw)
    try:
        with clean_db.cursor() as cur:
            cur.execute(f"INSERT INTO job ({cols}) VALUES ({phs}) RETURNING id", kw)
            rid = cur.fetchone()["id"]
        clean_db.commit()
        return rid
    except psycopg.Error:
        # psycopg3 不会自动回滚：失败后事务 aborted，须回滚再向上抛出约束错误
        clean_db.rollback()
        raise


def test_content_hash_unique(clean_db):
    sid = _source(clean_db)
    _insert_job(clean_db, **_job_kwargs(sid))
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_job(clean_db, **_job_kwargs(sid, title="另一个标题"))


def test_public_job_page_requires_url(clean_db):
    sid = _source(clean_db)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_job(clean_db, **_job_kwargs(sid, source_url=None))


def test_user_submitted_requires_market_analysis_consent(clean_db):
    sid = _source(clean_db, source_type="user_submitted", source_name="u1", covers_market="china")
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_job(clean_db, **_job_kwargs(
            sid, source_type="user_submitted", source_url=None, consent_status=None))
    # consent=none 同样被拒（B1：未授权贡献数据永不入库）
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_job(clean_db, **_job_kwargs(
            sid, source_type="user_submitted", source_url=None, consent_status="none"))
    # consent=market_analysis 通过
    jid = _insert_job(clean_db, **_job_kwargs(
        sid, source_type="user_submitted", source_url=None,
        consent_status="market_analysis", content_hash="h2"))
    assert jid > 0


def test_market_enum_restricted(clean_db):
    sid = _source(clean_db)
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_job(clean_db, **_job_kwargs(sid, market="mixed"))


def test_collected_at_not_null(clean_db):
    sid = _source(clean_db)
    with pytest.raises(psycopg.errors.NotNullViolation):
        _insert_job(clean_db, **_job_kwargs(sid, collected_at=None))


def test_snapshot_requires_sample_size_30(clean_db):
    with pytest.raises(psycopg.errors.CheckViolation):
        with clean_db.cursor() as cur:
            cur.execute(
                "INSERT INTO market_snapshot (scope, sample_size, skill_frequency,"
                " source_distribution, confidence, method_version)"
                " VALUES ('{}'::jsonb, 29, '[]'::jsonb, '{}'::jsonb, 'low', 'v0')")
    clean_db.rollback()


def test_jd_embedding_accepts_vector_no_index(clean_db):
    sid = _source(clean_db)
    jid = _insert_job(clean_db, **_job_kwargs(sid))
    with clean_db.cursor() as cur:
        cur.execute(
            "INSERT INTO jd_embedding (job_id, model, dim, embedding)"
            " VALUES (%s, 'test-model', 3, %s::vector)", (jid, "[1,2,3]"))
    clean_db.commit()
