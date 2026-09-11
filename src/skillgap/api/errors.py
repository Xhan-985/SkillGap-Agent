"""统一业务错误（API.md §0 错误体载体——routes 抛出，app.py handler 格式化）。

独立模块原因：app.py 需 import 各 routes 挂载，routes 需 import ApiError——
放 app.py 会循环导入。
"""
from __future__ import annotations


class ApiError(Exception):
    """业务错误 → 统一错误体 {"error": {"code", "message", "details"}}。"""

    def __init__(self, status_code: int, code: str, message: str,
                 details: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
