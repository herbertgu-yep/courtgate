"""同步版 Lua 加载器（Celery worker 用）。"""

from __future__ import annotations

from pathlib import Path

import redis as sync_redis

_LUA_DIR = Path(__file__).parent / "lua"
_sha_cache: dict[str, str] = {}


def _load(name: str) -> str:
    return (_LUA_DIR / name).read_text(encoding="utf-8")


def run_lua_sync(r: sync_redis.Redis, name: str, keys_list: list[str], argv: list) -> int:
    if name not in _sha_cache:
        _sha_cache[name] = r.script_load(_load(name))
    try:
        result = r.evalsha(_sha_cache[name], len(keys_list), *keys_list, *argv)
    except Exception as e:  # noqa: BLE001
        if "NOSCRIPT" in str(e):
            _sha_cache[name] = r.script_load(_load(name))
            result = r.evalsha(_sha_cache[name], len(keys_list), *keys_list, *argv)
        else:
            raise
    return int(result)
