"""可约时段的占用与归还：Redis 集合 + Lua 原子操作；对账以数据库为准。"""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import keys
from app.cache.lua_loader import run_lua
from app.core.exceptions import PerUserLimitExceededError, SlotUnavailableError
from app.core.logging import get_logger
from app.core.metrics import slot_drift_total, slots_released_total
from app.models import CourtSlot

log = get_logger("courtgate.slot")


async def init_available(redis: Redis, session: AsyncSession, release_id: int) -> int:
    """从数据库重建 Redis 可用集合（DEL + SADD，可重复执行）。"""
    rows = await session.scalars(
        select(CourtSlot.id).where(CourtSlot.release_id == release_id, CourtSlot.status == "free")
    )
    slot_ids = [str(i) for i in rows.all()]
    key = keys.avail_set(release_id)
    await redis.delete(key)
    await redis.delete(keys.slots_view(release_id))
    if slot_ids:
        await redis.sadd(key, *slot_ids)
        await redis.expire(key, 60 * 60 * 24 * 30)
    else:
        # 全部售罄：Redis 空集合会被自动删除，写标记防止每请求回源重建
        await redis.set(keys.depleted(release_id), 1, ex=60 * 60 * 24 * 30)
    return len(slot_ids)


async def claim(
    redis: Redis,
    *,
    release_id: int,
    user_id: int,
    slot_ids: list[int],
    per_user_limit: int,
    session: AsyncSession,
) -> None:
    """原子抢占。失败抛业务异常，成功静默。集合缺失时从数据库重建后重试一次。"""
    result = await run_lua(
        redis,
        "slot_claim.lua",
        [keys.avail_set(release_id), keys.bought_count(user_id, release_id)],
        [len(slot_ids), per_user_limit, *[str(i) for i in slot_ids]],
    )
    if result == 3:
        # 未初始化（Redis 重启/丢键/售罄标记存在）：重建后重试一次
        await init_available(redis, session, release_id)
        if await redis.exists(keys.depleted(release_id)):
            from app.core.metrics import slot_claim_failed_total

            slot_claim_failed_total.labels(reason="sold_out").inc()
            raise SlotUnavailableError(details={"sold_out": True})
        result = await run_lua(
            redis,
            "slot_claim.lua",
            [keys.avail_set(release_id), keys.bought_count(user_id, release_id)],
            [len(slot_ids), per_user_limit, *[str(i) for i in slot_ids]],
        )
    if result == 1:
        from app.core.metrics import slot_claim_failed_total

        slot_claim_failed_total.labels(reason="unavailable").inc()
        raise SlotUnavailableError(details={"court_slot_ids": slot_ids})
    if result == 2:
        from app.core.metrics import slot_claim_failed_total

        slot_claim_failed_total.labels(reason="limit").inc()
        raise PerUserLimitExceededError(details={"per_user_limit": per_user_limit})
    if result != 0:
        raise SlotUnavailableError(details={"reason": f"claim returned {result}"})


async def release(redis: Redis, *, release_id: int, user_id: int, slot_ids: list[int]) -> None:
    """归还：单元加回集合、限购计数减回。集合缺失时跳过（对账会重建）。"""
    result = await run_lua(
        redis,
        "slot_release.lua",
        [keys.avail_set(release_id), keys.bought_count(user_id, release_id)],
        [len(slot_ids), *[str(i) for i in slot_ids]],
    )
    if result == 0:
        slots_released_total.inc(len(slot_ids))


async def reconcile(redis: Redis, session: AsyncSession, release_id: int) -> int:
    """对账：数据库 free 集合 vs Redis 集合，不一致以数据库为准重建。返回差异数。"""
    db_free = set(
        (
            await session.scalars(
                select(CourtSlot.id).where(CourtSlot.release_id == release_id, CourtSlot.status == "free")
            )
        ).all()
    )
    key = keys.avail_set(release_id)
    redis_ids = {int(i) for i in await redis.smembers(key)}
    if redis_ids != db_free:
        drift = len(db_free.symmetric_difference(redis_ids))
        log.warning(
            "slot_drift_detected", release_id=release_id, db_count=len(db_free), redis_count=len(redis_ids), drift=drift
        )
        slot_drift_total.inc()
        await redis.delete(key)
        if db_free:
            await redis.sadd(key, *[str(i) for i in db_free])
        await redis.expire(key, 60 * 60 * 24 * 30)
        await redis.delete(keys.slots_view(release_id))
        return drift
    return 0
