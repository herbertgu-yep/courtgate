"""并发正确性：本项目最重要的测试。

T1 批量抢占不超卖 / T2 单时段并发 / T3 多时段原子性 / T5 幂等并发
以及「先查后占」丢失更新的演示（为什么必须 Redis 原子操作）。
"""

import asyncio
import datetime as dt
import uuid

import pytest
from sqlalchemy import text

from app.cache.redis_client import get_async_redis
from app.core.exceptions import (
    CourtGateError,
    IdempotencyConflictError,
    PerUserLimitExceededError,
    SlotUnavailableError,
)
from app.db.session import AsyncSessionLocal
from app.services import booking_service
from tests.conftest import make_operator, make_release, make_venue

T1_CONCURRENCY = int(__import__("os").environ.get("T1_CONCURRENCY", "120"))


async def _setup_release(client, *, n_courts: int = 2, n_slots: int = 3, n_days: int = 1):
    op = await make_operator(client)
    venue_id, courts, _ = await make_venue(client, op, n_courts=n_courts, n_slots=n_slots)
    info = await make_release(client, op, venue_id, n_days=n_days)
    return info


async def _make_users(n: int) -> list[int]:
    """批量造用户（直插数据库，不走 HTTP）。"""
    from app.core.security import hash_password
    from app.models import User

    users = []
    async with AsyncSessionLocal() as s:
        for i in range(n):
            u = User(
                username=f"bench_{int(dt.datetime.now().timestamp()) % 10**6}_{i}",
                password_hash=hash_password("Pass@123"),
                nickname=f"u{i}",
            )
            s.add(u)
            users.append(u)
        await s.commit()
        ids = [u.id for u in users]
    return ids


async def _try_book(user_id: int, release_id: int, slot_ids: list[int]) -> tuple[bool, Exception | None]:
    """独立会话的一次预约尝试。返回 (是否成功, 异常)。"""
    redis = get_async_redis()
    key = str(uuid.uuid4())
    try:
        async with AsyncSessionLocal() as session:
            await booking_service.create_booking(
                session, redis, user_id=user_id, release_id=release_id, court_slot_ids=slot_ids, idempotency_key=key
            )
        return True, None
    except (CourtGateError, Exception) as e:  # noqa: BLE001
        return False, e


@pytest.mark.asyncio
async def test_t1_batch_grab_no_oversell(client) -> None:
    """N 人并发抢 M 个时段 → 恰好 M 单成功，无单元被重复占用。"""
    info = await _setup_release(client, n_courts=2, n_slots=3, n_days=1)  # 6 个单元
    total_slots = info["available"]
    users = await _make_users(T1_CONCURRENCY)
    r = await client.get(f"/api/releases/{info['release_id']}/slots")
    all_ids = [s["court_slot_id"] for c in r.json()["courts"] for s in c["slots"]]

    results = await asyncio.gather(
        *[_try_book(uid, info["release_id"], [all_ids[i % len(all_ids)]]) for i, uid in enumerate(users)]
    )
    ok = [x for x, _ in results if x]
    assert len(ok) == total_slots, f"应恰好 {total_slots} 单成功，实际 {len(ok)}"

    # 无单元被重复占用：每个 court_slot 只属于一张预约单
    from app.db.sync_session import sync_engine

    with sync_engine.connect() as conn:
        dup = conn.execute(
            text(
                "SELECT court_slot_id, COUNT(DISTINCT booking_no) c FROM booking_items "
                "GROUP BY court_slot_id HAVING c > 1"
            )
        ).fetchall()
        assert not dup, f"重复占用: {dup}"
        booked = conn.execute(text("SELECT COUNT(*) FROM court_slots WHERE status='booked'")).scalar()
        assert booked == total_slots


@pytest.mark.asyncio
async def test_t2_same_slot_one_winner(client) -> None:
    """N 人并发抢同一时段 → 恰好 1 人成功。"""
    info = await _setup_release(client, n_courts=1, n_slots=1, n_days=1)
    users = await _make_users(50)
    r = await client.get(f"/api/releases/{info['release_id']}/slots")
    sid = [s["court_slot_id"] for c in r.json()["courts"] for s in c["slots"]][0]

    results = await asyncio.gather(*[_try_book(uid, info["release_id"], [sid]) for uid in users])
    winners = [x for x, _ in results if x]
    assert len(winners) == 1
    # 其余全部是"已被预约"而非服务器错误
    for ok, err in results:
        if not ok:
            assert isinstance(err, SlotUnavailableError), f"应返回业务冲突而非异常: {err!r}"


@pytest.mark.asyncio
async def test_t3_multi_slot_atomicity(client) -> None:
    """请求 [已占, 空闲] → 全部失败，空闲时段未被占用。"""
    info = await _setup_release(client, n_courts=1, n_slots=2, n_days=1)
    r = await client.get(f"/api/releases/{info['release_id']}/slots")
    ids = [s["court_slot_id"] for c in r.json()["courts"] for s in c["slots"]]
    s1, s2 = ids[0], ids[1]

    # 先占掉 s1
    users = await _make_users(2)
    ok, _ = await _try_book(users[0], info["release_id"], [s1])
    assert ok

    # 另一人请求 [s1(已占), s2(空闲)] → 整单失败，s2 仍是 free
    ok2, err = await _try_book(users[1], info["release_id"], [s1, s2])
    assert not ok2 and isinstance(err, SlotUnavailableError)
    from app.db.sync_session import sync_engine

    with sync_engine.connect() as conn:
        st = conn.execute(text("SELECT status FROM court_slots WHERE id=:i"), {"i": s2}).scalar()
    assert st == "free", "空闲时段不应被部分占用"


@pytest.mark.asyncio
async def test_t5_idempotent_concurrent(client) -> None:
    """同幂等键并发 N 次 → 只 1 张预约单，单元只占一次。"""
    info = await _setup_release(client, n_courts=1, n_slots=2, n_days=1)
    users = await _make_users(30)
    r = await client.get(f"/api/releases/{info['release_id']}/slots")
    sid = [s["court_slot_id"] for c in r.json()["courts"] for s in c["slots"]][0]
    key = str(uuid.uuid4())

    redis = get_async_redis()

    async def one(uid: int):
        try:
            async with AsyncSessionLocal() as session:
                out = await booking_service.create_booking(
                    session,
                    redis,
                    user_id=uid,
                    release_id=info["release_id"],
                    court_slot_ids=[sid],
                    idempotency_key=key,
                )
            return ("ok", out["booking_no"])
        except CourtGateError as e:
            return ("conflict", e)

    results = await asyncio.gather(*[one(uid) for uid in users])
    nos = {no for status, no in results if status == "ok"}
    # 只有一张预约单（成功者返回同一单号，其余为幂等冲突）
    assert len(nos) == 1, f"应只产生 1 张预约单，实际 {len(nos)}"
    conflicts = [e for s, e in results if s == "conflict"]
    assert all(
        isinstance(e, (IdempotencyConflictError, SlotUnavailableError, PerUserLimitExceededError)) for e in conflicts
    )


@pytest.mark.asyncio
async def test_lost_update_demo_check_then_act(client) -> None:
    """演示：先查后占（无条件写）在并发下丢失更新——同一时段的归属被覆盖。

    这是「为什么必须 Redis 原子操作」的实证。确定性构造：
    事务 A 读到 free → 事务 B 也读到 free（MVCC 快照）→ A 先提交 →
    B 的无条件覆盖随后生效 → A 的占用被无声抹掉。
    """
    info = await _setup_release(client, n_courts=1, n_slots=1, n_days=1)
    r = await client.get(f"/api/releases/{info['release_id']}/slots")
    sid = [s["court_slot_id"] for c in r.json()["courts"] for s in c["slots"]][0]

    s_a = AsyncSessionLocal()
    s_b = AsyncSessionLocal()
    # 各自开启事务并读到 free（REPEATABLE READ 快照）
    a_status = (await s_a.execute(text("SELECT status FROM court_slots WHERE id=:i"), {"i": sid})).scalar()
    b_status = (await s_b.execute(text("SELECT status FROM court_slots WHERE id=:i"), {"i": sid})).scalar()
    assert a_status == "free" and b_status == "free"

    # 事务 A：无条件写 + 提交（此时持有行锁）
    await s_a.execute(text("UPDATE court_slots SET status='booked', booking_no='BN_AAA' WHERE id=:i"), {"i": sid})
    await s_a.commit()
    # 事务 B：在 A 提交后执行覆盖写（快照读仍见 free，写不加状态条件）
    await s_b.execute(text("UPDATE court_slots SET status='booked', booking_no='BN_BBB' WHERE id=:i"), {"i": sid})
    await s_b.commit()
    await s_a.close()
    await s_b.close()

    from app.db.sync_session import sync_engine

    with sync_engine.connect() as conn:
        final = conn.execute(text("SELECT booking_no FROM court_slots WHERE id=:i"), {"i": sid}).scalar()
    # 先到者的占用被后到者无声覆盖——这正是朴素实现超卖/错乱的根源
    assert final == "BN_BBB"
