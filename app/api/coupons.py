"""优惠券路由：可领列表 / 领取 / 我的券。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_redis, get_session
from app.models import CouponTemplate, User, UserCoupon
from app.services import coupon_service, rate_limit

router = APIRouter(prefix="/api/coupons", tags=["优惠券"])


@router.get("/templates", summary="可领券列表")
async def templates(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    rows = (await session.scalars(select(CouponTemplate).where(CouponTemplate.status == "active"))).all()
    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "type": t.type,
                "value": t.value,
                "min_spend_cents": t.min_spend_cents,
                "remaining": t.total_quantity - t.claimed_count,
                "per_user_limit": t.per_user_limit,
                "valid_from": t.valid_from,
                "valid_to": t.valid_to,
            }
            for t in rows
        ]
    }


@router.post("/{template_id}/claim", summary="领券（限量抢占）", status_code=201)
async def claim(
    template_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    await rate_limit.check(redis, scope="claim", user_id=user.id)
    out = await coupon_service.claim(session, redis, user_id=user.id, template_id=template_id)
    return out


@router.get("/mine", summary="我的券")
async def mine(
    session: Annotated[AsyncSession, Depends(get_session)], user: Annotated[User, Depends(get_current_user)]
) -> dict:
    rows = (
        await session.scalars(select(UserCoupon).where(UserCoupon.user_id == user.id).order_by(UserCoupon.id.desc()))
    ).all()
    tpl_ids = list({c.template_id for c in rows})
    tpls = {
        t.id: t for t in (await session.scalars(select(CouponTemplate).where(CouponTemplate.id.in_(tpl_ids)))).all()
    }
    return {
        "items": [
            {
                "id": c.id,
                "code": c.code,
                "status": c.status,
                "template_id": c.template_id,
                "booking_no": c.booking_no,
                "expire_at": c.expire_at,
                "name": (tpls.get(c.template_id) or CouponTemplate()).name,
                "type": (tpls.get(c.template_id) or CouponTemplate()).type,
                "value": (tpls.get(c.template_id) or CouponTemplate()).value,
                "min_spend_cents": (tpls.get(c.template_id) or CouponTemplate()).min_spend_cents,
            }
            for c in rows
        ]
    }
