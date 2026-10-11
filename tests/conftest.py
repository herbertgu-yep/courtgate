"""测试地基：独立测试库 courtgate_test + Redis db15，每测清空。

连接串通过环境变量在导入 app 之前注入，settings 的 lru_cache 在此后才首次生效。
"""

from __future__ import annotations

import os

os.environ.setdefault(
    "COURTGATE_DATABASE_URL", "mysql+aiomysql://root:root@localhost:3306/courtgate_test?charset=utf8mb4"
)
os.environ.setdefault(
    "COURTGATE_SYNC_DATABASE_URL", "mysql+pymysql://root:root@localhost:3306/courtgate_test?charset=utf8mb4"
)
os.environ.setdefault("COURTGATE_REDIS_URL", "redis://localhost:6379/15")
os.environ["COURTGATE_RATE_LIMIT_ENABLED"] = "false"
os.environ["COURTGATE_BOOKING_EXPIRE_SECONDS"] = "900"
os.environ["COURTGATE_DB_POOL_SIZE"] = "40"
os.environ["COURTGATE_DB_MAX_OVERFLOW"] = "60"

import contextlib  # noqa: E402

import pymysql  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

TABLES = [
    "notifications",
    "points_ledger",
    "user_coupons",
    "coupon_templates",
    "oauth_accounts",
    "member_levels",
    "stock_flows",
    "booking_items",
    "bookings",
    "payments",
    "court_slots",
    "releases",
    "time_slots",
    "courts",
    "venues",
    "users",
]


def _prepare_db() -> None:
    conn = pymysql.connect(host="localhost", user="root", password="root")
    with conn.cursor() as cur:
        cur.execute(
            "CREATE DATABASE IF NOT EXISTS courtgate_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    conn.commit()
    conn.close()
    # 建表：测试直接 create_all（生产用 Alembic，测试只关心当轮结构）
    from app.db.sync_session import sync_engine
    from app.models import Base

    Base.metadata.create_all(sync_engine)


@pytest.fixture(scope="session", autouse=True)
def _prepare() -> None:
    _prepare_db()


@pytest.fixture(autouse=True)
async def _clean() -> AsyncIterator[None]:
    """每个测试前清空业务表 + FLUSHDB。

    TRUNCATE 需要元数据锁：上一个测试若泄漏了带打开事务的连接，会永久阻塞，
    因此先 KILL 测试库的全部遗留连接（自己除外）。
    """
    from app.db.sync_session import sync_engine

    with sync_engine.connect() as conn:
        stale = conn.execute(
            text("SELECT id FROM information_schema.processlist WHERE db = 'courtagate_test' AND id <> CONNECTION_ID()")
        ).fetchall()
        for (pid,) in stale:
            with contextlib.suppress(Exception):
                conn.execute(text(f"KILL {pid}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for t in TABLES:
            conn.execute(text(f"DELETE FROM {t}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        conn.commit()
    from app.cache.redis_client import get_async_redis

    r = get_async_redis()
    await r.flushdb()
    yield


@pytest.fixture
async def client() -> AsyncIterator:
    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def _solve_captcha(client: AsyncClient) -> dict:
    """获取图形验证码，并从 Redis 读取答案（集成测试的正当做法：验证生成与存储链路）。"""
    from app.cache.redis_client import get_async_redis

    cap = (await client.get("/api/auth/captcha")).json()
    answer = await get_async_redis().get(f"cg:captcha:{cap['captcha_id']}")
    return {"captcha_id": cap["captcha_id"], "captcha_code": answer}


async def register_and_login(
    client: AsyncClient, username: str, password: str = "Pass@123", nickname: str = ""
) -> dict:
    """注册（图形验证码）→ 登录（图形验证码）→ 返回令牌。"""
    cap = await _solve_captcha(client)
    await client.post(
        "/api/auth/register", json={"username": username, "password": password, "nickname": nickname, **cap}
    )
    cap2 = await _solve_captcha(client)
    r = await client.post("/api/auth/login", json={"username": username, "password": password, **cap2})
    return r.json()


# ---------------------------------------------------------------- 数据工厂


async def make_operator(client: AsyncClient) -> dict:
    """注册一个管理员并返回其请求头。"""
    tokens = await register_and_login(client, "13900000001", nickname="管理员")
    from sqlalchemy import update

    from app.db.session import AsyncSessionLocal
    from app.models import User

    async with AsyncSessionLocal() as s:
        await s.execute(update(User).where(User.username == "13900000001").values(role="operator"))
        await s.commit()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def make_venue(
    client: AsyncClient, op_headers: dict, *, name: str = "星羽羽毛球馆", n_courts: int = 12, n_slots: int = 14
) -> tuple[int, list[int], list[int]]:
    """按新版接口建场馆（含场地）；时段由营业配置在放场时切片，返回 (venue_id, court_ids, [])。

    n_slots 仅为兼容旧签名保留：08:00-22:00 + 60 分钟粒度天然切出 14 段（18-22 点高峰 1.5 倍）。
    """
    r = await client.post(
        "/api/admin/venues",
        json={
            "name": name,
            "address": "东区",
            "phone": "",
            "open_time": "08:00",
            "close_time": "22:00",
            "breaks": [],
            "slot_minutes": 60,
            "court_count": n_courts,
            "base_price_cents": 3000,
        },
        headers=op_headers,
    )
    assert r.status_code == 201, r.text
    venue_id = r.json()["id"]
    detail = (await client.get(f"/api/admin/venues/{venue_id}", headers=op_headers)).json()
    court_ids = [c["id"] for c in detail["courts"]]
    return venue_id, court_ids, []


import datetime as dt  # noqa: E402


def _iso_open() -> dict:
    """一个当前已开放、7 天周期、每人限 3 的放场参数。"""
    now = dt.datetime.now(dt.UTC)
    return {
        "name": "第 41 周放场",
        "period_start": str(now.date() + dt.timedelta(days=1)),
        "period_end": str(now.date() + dt.timedelta(days=7)),
        "open_at": (now - dt.timedelta(hours=1)).isoformat(timespec="seconds"),
        "close_at": (now + dt.timedelta(days=8)).isoformat(timespec="seconds"),
        "per_user_limit": 3,
    }


async def make_release(client: AsyncClient, op_headers: dict, venue_id: int, *, n_days: int = 7, **overrides) -> dict:
    import datetime as dt

    body = {**_iso_open(), **overrides}
    body["venue_id"] = venue_id
    start = dt.datetime.now(dt.UTC).date() + dt.timedelta(days=1)
    body["period_start"] = str(start)
    body["period_end"] = str(start + dt.timedelta(days=n_days - 1))
    r = await client.post("/api/admin/releases", json=body, headers=op_headers)
    return r.json()


from collections.abc import AsyncIterator  # noqa: E402
