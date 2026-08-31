"""数据库连接与 SQL 迁移执行（ADR-010：版本化 .sql 文件，幂等可重放）。"""
from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg.rows import DictRow, dict_row

from skillgap.config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"


def connect(url: str | None = None) -> psycopg.Connection[DictRow]:
    return psycopg.connect(url or settings.database_url, row_factory=dict_row)


def upgrade(conn: psycopg.Connection) -> list[str]:
    """按文件名顺序应用未执行的迁移，返回本次应用的迁移名列表。"""
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        cur.execute("SELECT name FROM schema_migrations")
        applied = {row["name"] for row in cur.fetchall()}
    conn.commit()

    applied_now: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(sql)
                cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        applied_now.append(path.name)
    return applied_now


def ensure_database(admin_url: str, db_name: str) -> None:
    """测试辅助：不存在则创建数据库（连接到 postgres 库执行 CREATE DATABASE）。"""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{db_name}"')
