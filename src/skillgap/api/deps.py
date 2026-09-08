"""依赖注入（D1：每请求连接，本地单用户不引入连接池——Phase 11 复议点）。"""
from __future__ import annotations

from collections.abc import Generator

import psycopg
from psycopg.rows import DictRow

from skillgap import db


def get_conn() -> Generator[psycopg.Connection[DictRow], None, None]:
    """每请求新建连接，请求结束关闭（测试经 dependency_overrides 注入 test 库连接）。"""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()
