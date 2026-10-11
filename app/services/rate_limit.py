"""滑动窗口限流：按用户 + 按 IP。"""

from __future__ import annotations

import time
import uuid

from redis.asyncio import Redis

from app.cache import keys
from app.cache.lua_loader import run_lua
from app.core.config import get_settings
from app.core.exceptions import RateLimitedError

# scope -> (窗口秒, 上限)
RULES: dict[str, tuple[int, int]] = {
    "booking": (10, 10),  # 预约：每用户 10 秒 10 次
    "login": (60, 10),  # 登录：每 IP 60 秒 10 次
    "claim": (10, 10),  # 领券
}


async def check(redis: Redis, *, scope: str, user_id: int | None = None, ip: str | None = None) -> None:
    """超限抛 RateLimitedError；通过则静默。"""
    if not get_settings().rate_limit_enabled:
        return
    if scope not in RULES:
        return
    window_sec, limit = RULES[scope]
    window_ms = window_sec * 1000
    now_ms = int(time.time() * 1000)
    member = f"{now_ms}-{uuid.uuid4().hex[:8]}"
    key = keys.rate_limit_user(user_id) if user_id else keys.rate_limit_ip(ip or "unknown")
    ok = await run_lua(redis, "rate_limit.lua", [key], [window_ms, limit, now_ms, member])
    if ok == 0:
        from app.core.metrics import rate_limited_total

        rate_limited_total.labels(scope=scope).inc()
        raise RateLimitedError(details={"scope": scope, "window_seconds": window_sec, "limit": limit})

        rate_limited_total.labels(scope=scope).inc()
        raise RateLimitedError(details={"scope": scope, "window_seconds": window_sec, "limit": limit})
