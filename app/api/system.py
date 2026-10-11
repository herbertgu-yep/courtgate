"""系统路由：健康检查 + 指标。"""

from __future__ import annotations

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.metrics import http_request_duration, http_requests_total

router = APIRouter(tags=["系统"])


@router.get("/healthz", summary="健康检查（MySQL + Redis）")
async def healthz() -> JSONResponse:
    from sqlalchemy import text

    from app.cache.redis_client import get_async_redis
    from app.db.session import engine

    status: dict = {"status": "ok", "mysql": "ok", "redis": "ok"}
    code = 200
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        status["mysql"] = "down"
        status["status"] = "degraded"
        code = 503
    try:
        await get_async_redis().ping()
    except Exception:  # noqa: BLE001
        status["redis"] = "down"
        status["status"] = "degraded"
        code = 503
    return JSONResponse(content=status, status_code=code)


@router.get("/metrics", summary="Prometheus 指标")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_http(method: str, path: str, status: int, duration: float) -> None:
    http_requests_total.labels(method=method, path=path, status=str(status)).inc()
    http_request_duration.labels(method=method, path=path).observe(duration)
