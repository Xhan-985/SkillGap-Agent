from __future__ import annotations

import os

import psycopg
import pytest

from skillgap import db
from skillgap.config import settings
from skillgap.taxonomy.seed import seed_all

TEST_URL = os.environ.get("TEST_DATABASE_URL", settings.test_database_url)
ADMIN_URL = "postgresql://skillgap:skillgap@localhost:5432/postgres"


@pytest.fixture(scope="session")
def db_conn():
    try:
        db.ensure_database(ADMIN_URL, TEST_URL.rsplit("/", 1)[-1])
        conn = psycopg.connect(TEST_URL, row_factory=psycopg.rows.dict_row)
    except psycopg.OperationalError:
        pytest.skip("PostgreSQL 不可用（docker compose up -d postgres）")
    db.upgrade(conn)
    seed_all(conn)
    yield conn
    conn.close()


DATA_TABLES = [
    "job_skill", "new_skill_candidate", "deletion_code", "jd_embedding",
    "match_result", "recommendation", "candidate_evidence", "candidate_skill",
    "candidate", "job", "company", "raw_jobs", "ingest_batch",
    "ingest_checkpoint", "ingest_request_log", "market_snapshot",
    "llm_cache", "eval_run", "evaluation_sample",
]


@pytest.fixture()
def clean_db(db_conn):
    """每个测试清空数据表（保留 skill/词表/data_source 种子）。"""
    # 上一测试若以预期内的约束报错收尾，事务处于 aborted 状态，先回滚再清表
    db_conn.rollback()
    with db_conn.cursor() as cur:
        cur.execute(
            f"TRUNCATE {', '.join(DATA_TABLES)} RESTART IDENTITY CASCADE"
        )
    db_conn.commit()
    return db_conn
