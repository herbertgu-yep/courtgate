"""Redis 客户端：async（Web）与 sync（Celery）。"""

from __future__ import annotations

from typing import Any

import redis as sync_redis
import redis.asyncio as aioredis

from app.core.config import get_settings

_async_pool: aioredis.Redis | None = None
_sync_pool: sync_redis.Redis | None = None


def _conf() -> dict[str, Any]:
    return {"url": get_settings().redis_url, "decode_responses": True}


def get_async_redis() -> aioredis.Redis:
    global _async_pool
    if _async_pool is None:
        _async_pool = aioredis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            max_connections=int(__import__("os").environ.get("COURTGATE_REDIS_MAX_CONN", "200")),
        )
    return _async_pool


def get_sync_redis() -> sync_redis.Redis:
    global _sync_pool
    if _sync_pool is None:
        _sync_pool = sync_redis.Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _sync_pool
