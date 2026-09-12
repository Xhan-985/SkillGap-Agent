"""FastAPI 应用工厂（Phase 10 T1 骨架——health + 统一错误体，业务路由随 T2-T5 增补）。

API 层纪律（D3）：零计算，只组装既有 service 层输出并按 API.md 契约裁剪。
统一错误体（API.md §0）：{"error": {"code", "message", "details"}}。
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from skillgap.api.deps import get_conn
from skillgap.api.errors import ApiError
from skillgap.config import settings


def _error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def create_app() -> FastAPI:
    app = FastAPI(title="SkillGap Agent API", docs_url="/api/docs")

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code,
                            content=_error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", "请求参数校验失败",
                                {"errors": exc.errors()[:10]}))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: StarletteHTTPException):
        code = "NOT_FOUND" if exc.status_code in (404, 405) else "DB_ERROR"
        return JSONResponse(status_code=exc.status_code,
                            content=_error_body(code, str(exc.detail)))

    @app.get("/api/health")
    def health(conn=Depends(get_conn)):
        """§2.16：llm 字段报告 key 配置状态而非真实探活（健康检查不触发付费调用）。"""
        try:
            conn.execute("SELECT 1")
            db_ok = True
        except Exception:
            db_ok = False
        return {"status": "ok" if db_ok else "degraded", "db": db_ok,
                "llm": "configured" if settings.llm_api_key else "not_configured"}

    from skillgap.api.routes_market import router as market_router
    app.include_router(market_router)
    from skillgap.api.routes_profile import router as profile_router
    app.include_router(profile_router)
    from skillgap.api.routes_match import router as match_router
    app.include_router(match_router)

    return app
