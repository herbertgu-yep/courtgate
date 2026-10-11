"""CourtGate 主应用：路由注册、请求 ID 中间件、指标、静态托管。"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app.api import admin, auth, bookings, coupons, members, notifications, payments, system, venues
from app.api.system import record_http
from app.core.config import get_settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import new_request_id, setup_logging


def create_app() -> FastAPI:
    s = get_settings()
    setup_logging(s.log_level)

    app = FastAPI(title="CourtGate", version="0.1.0", docs_url="/docs", redoc_url=None)

    app.include_router(auth.router)
    app.include_router(venues.router)
    app.include_router(bookings.router)
    app.include_router(payments.router)
    app.include_router(coupons.router)
    app.include_router(members.router)
    app.include_router(notifications.router)
    app.include_router(admin.router)
    app.include_router(system.router)

    register_error_handlers(app)

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Any:
        rid = new_request_id()
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        path = request.url.path
        if path.startswith("/api") or path == "/healthz":
            record_http(request.method, path, response.status_code, duration)
        response.headers["X-Request-ID"] = rid
        # UI 资源不缓存：开发模式改完即生效，线上由版本号控制刷新
        path = request.url.path
        if not path.startswith(("/api", "/metrics")) and (
            path.endswith((".html", ".js", ".css")) or "." not in path.rsplit("/", 1)[-1]
        ):
            response.headers["Cache-Control"] = "no-cache"
        return response

    if s.ui_enabled:
        ui_dir = Path(__file__).resolve().parent.parent / "ui"
        if ui_dir.exists():
            app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app


app = create_app()
