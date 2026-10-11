"""优惠券：领券（限量抢占）与核销（CAS 幂等）。"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import cast

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import keys
from app.cache.lua_loader import run_lua
from app.core.exceptions import CouponNotApplicableError, CouponSoldOutError, NotFoundError, PerUserLimitExceededError
from app.core.logging import get_logger
from app.core.metrics import coupons_claimed_total
from app.models import CouponTemplate, UserCoupon

log = get_logger("courtgate.coupon")


def gen_coupon_code() -> str:
    return f"CPN{secrets.token_urlsafe(12)}"


async def init_stock(redis: Redis, template_id: int, remaining: int) -> None:
    """初始化/重置券库存计数（以数据库为准）。"""
    key = keys.coupon_stock(template_id)
    await redis.set(key, max(0, remaining), ex=60 * 60 * 24 * 30)


async def claim(
    session: AsyncSession,
    redis: Redis,
    *,
    user_id: int,
    template_id: int,
) -> dict:
    """领券：Lua 原子预扣 → 落库（唯一约束兜底）。幂等：重复领返回已有券。"""
    tpl = await session.get(CouponTemplate, template_id)
    if tpl is None or tpl.status != "active":
        raise NotFoundError("券模板不存在或已下架")
    now = datetime.now(UTC)
    if not (tpl.valid_from.replace(tzinfo=UTC) <= now <= tpl.valid_to.replace(tzinfo=UTC)):
        raise CouponNotApplicableError("不在可领取时间范围内")

    existing = await session.scalar(
        select(UserCoupon).where(
            UserCoupon.user_id == user_id, UserCoupon.template_id == template_id, UserCoupon.status == "unused"
        )
    )
    if existing is not None:
        return {"coupon_id": existing.id, "code": existing.code}

    stock_key = keys.coupon_stock(template_id)
    if await redis.exists(stock_key) == 0:
        remaining = tpl.total_quantity - tpl.claimed_count
        await init_stock(redis, template_id, remaining)
    result = await run_lua(
        redis, "coupon_claim.lua", [stock_key, keys.coupon_claimed(template_id, user_id)], [tpl.per_user_limit]
    )
    if result == 1:
        raise CouponSoldOutError(details={"template_id": template_id})
    if result == 2:
        raise PerUserLimitExceededError(details={"per_user_limit": tpl.per_user_limit})

    code = gen_coupon_code()
    uc = UserCoupon(
        user_id=user_id, template_id=template_id, code=code, status="unused", claimed_at=now, expire_at=tpl.valid_to
    )
    session.add(uc)
    tpl.claimed_count += 1  # 持久化对象在会话内直接更新
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        # 数据库唯一约束兜底失败：回滚 Redis 计数
        await redis.incr(stock_key)
        await redis.decr(keys.coupon_claimed(template_id, user_id))
        raise
    coupons_claimed_total.labels(template_id=str(template_id)).inc()
    log.info("coupon_claimed", user_id=user_id, template_id=template_id)
    return {"coupon_id": uc.id, "code": code}


async def usable_coupon(session: AsyncSession, *, coupon_id: int, user_id: int) -> UserCoupon:
    uc = await session.get(UserCoupon, coupon_id)
    if uc is None or uc.user_id != user_id:
        raise NotFoundError("优惠券不存在")
    if uc.status != "unused":
        raise CouponNotApplicableError(details={"status": uc.status})
    return uc


async def redeem(session: AsyncSession, *, coupon_id: int, booking_no: str) -> None:
    """核销：CAS unused → used，防重复。"""
    res = cast(
        "CursorResult",
        session.execute(
            update(UserCoupon)
            .where(UserCoupon.id == coupon_id, UserCoupon.status == "unused")
            .values(status="used", booking_no=booking_no)
        ),
    )
    if res.rowcount != 1:
        raise CouponNotApplicableError(details={"coupon_id": coupon_id})


async def release(session: AsyncSession, *, booking_no: str) -> int | None:
    """取消预约时把券还回 unused。返回券 id（没有则 None）。"""
    uc = await session.scalar(
        select(UserCoupon).where(UserCoupon.booking_no == booking_no, UserCoupon.status == "used")
    )
    if uc is None:
        return None
    await session.execute(
        update(UserCoupon)
        .where(UserCoupon.id == uc.id, UserCoupon.status == "used")
        .values(status="unused", booking_no="")
    )
    return uc.id


async def mark_expired(session: AsyncSession) -> int:
    """过期任务：unused 且已过期 → expired。"""
    now = datetime.now(UTC)
    res = cast(
        "CursorResult",
        session.execute(
            update(UserCoupon)
            .where(UserCoupon.status == "unused", UserCoupon.expire_at < now.replace(tzinfo=None))
            .values(status="expired")
        ),
    )
    await session.commit()
    return res.rowcount or 0
