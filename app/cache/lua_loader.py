"""Lua 脚本加载器：启动时 SCRIPT LOAD 缓存 SHA，NOSCRIPT 自动重载。"""

from __future__ import annotations

from pathlib import Path

from redis.asyncio import Redis

_LUA_DIR = Path(__file__).parent / "lua"
_cache: dict[str, str] = {}


def _load(name: str) -> str:
    if name not in _cache:
        _cache[name] = (_LUA_DIR / name).read_text(encoding="utf-8")
    return _cache[name]


async def run_lua(redis: Redis, name: str, keys_list: list[str], argv: list[str | int]) -> int:
    """EVALSHA 优先；收到 NOSCRIPT 时重新 LOAD 再试一次。"""
    try:
        result = await redis.evalsha(await _sha(redis, name), len(keys_list), *keys_list, *argv)
    except Exception as e:  # noqa: BLE001
        if "NOSCRIPT" in str(e):
            _sha_cache.pop(name, None)
            result = await redis.evalsha(await _sha(redis, name), len(keys_list), *keys_list, *argv)
        else:
            raise
    return int(result)


_sha_cache: dict[str, str] = {}


async def _sha(redis: Redis, name: str) -> str:
    if name not in _sha_cache:
        _sha_cache[name] = await redis.script_load(_load(name))
    return _sha_cache[name]
