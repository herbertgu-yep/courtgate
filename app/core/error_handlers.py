"""全局异常 → 统一错误体。api 层不 try/except。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import CourtGateError

log = logging.getLogger("courtgate.error")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(CourtGateError)
    async def on_business_error(_: Request, exc: CourtGateError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": {"code": exc.code, "message": exc.detail, "details": exc.details}},
        )

    @app.exception_handler(RequestValidationError)
    async def on_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {"code": "VALIDATION_ERROR", "message": "参数不合法", "details": {"errors": exc.errors()[:5]}}
            },
        )

    @app.exception_handler(Exception)
    async def on_unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error: %s", exc)
        # 不把堆栈返回给客户端
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "服务器内部错误", "details": {}}},
        )
