"""预约路由：幂等下单 / 我的预约 / 详情 / 取消。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_redis, get_session
from app.models import Booking, BookingItem, User
from app.schemas.booking import BookingIn
from app.services import rate_limit
from app.services.booking_service import cancel_by_user_with_refund, get_for_user, serialize
from app.services.booking_service import create_booking as _create_booking

router = APIRouter(prefix="/api/bookings", tags=["预约"])


@router.post("", summary="预约（需 Idempotency-Key 头）", status_code=201)
async def book_endpoint(
    body: BookingIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    if not idempotency_key:
        from app.core.exceptions import CourtGateError

        e = CourtGateError("缺少 Idempotency-Key 请求头")
        e.code = "VALIDATION_ERROR"
        e.http_status = 422
        raise e
    await rate_limit.check(redis, scope="booking", user_id=user.id)
    return await _create_booking(
        session,
        redis,
        user_id=user.id,
        release_id=body.release_id,
        court_slot_ids=body.court_slot_ids,
        idempotency_key=idempotency_key,
        coupon_id=body.coupon_id,
        use_points=body.use_points,
    )


@router.post("/quote", summary="预约试算（不落库）")
async def quote_booking(
    body: BookingIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """实时试算价格明细：不占用任何资源。"""
    from sqlalchemy import select as _select

    from app.models import CouponTemplate, Court, CourtSlot, TimeSlot, UserCoupon
    from app.services import member_service
    from app.services.pricing.engine import CouponView, quote

    if not body.court_slot_ids:
        from app.core.exceptions import CourtGateError

        raise CourtGateError("请先选择时段")
    slot_rows = (
        await session.execute(
            _select(CourtSlot, Court.name, TimeSlot.label, Court.venue_id)
            .join(Court, CourtSlot.court_id == Court.id)
            .join(TimeSlot, CourtSlot.time_slot_id == TimeSlot.id)
            .where(CourtSlot.id.in_(body.court_slot_ids), CourtSlot.release_id == body.release_id)
        )
    ).all()
    if len(slot_rows) != len(set(body.court_slot_ids)):
        from app.core.exceptions import NotFoundError

        raise NotFoundError("部分时段不存在或不属于该批次")
    from app.services import venue_service

    await venue_service.assert_dates_open(session, slot_rows[0][3], {r[0].slot_date for r in slot_rows})
    subtotal = sum(r[0].price_cents for r in slot_rows)

    level = await member_service.level_for(session, user.member_level)
    member_bp = level.discount_bp if level else 10000
    coupon_view = None
    if body.coupon_id is not None:
        uc = await session.get(UserCoupon, body.coupon_id)
        if uc is None or uc.user_id != user.id or uc.status != "unused":
            from app.core.exceptions import CouponNotApplicableError

            raise CouponNotApplicableError(details={"coupon_id": body.coupon_id})
        ct = await session.get(CouponTemplate, uc.template_id)
        assert ct is not None
        coupon_view = CouponView(
            type=ct.type, value=ct.value, min_spend_cents=ct.min_spend_cents, max_discount_cents=ct.max_discount_cents
        )
    from app.core.config import get_settings

    q = quote(
        subtotal_cents=subtotal,
        member_discount_bp=member_bp,
        coupon=coupon_view,
        use_points=body.use_points,
        user_points=user.points_balance,
        points_redeem_max_bp=get_settings().points_redeem_max_bp,
    )
    items = [
        {
            "court_slot_id": r[0].id,
            "date": str(r[0].slot_date),
            "court_name": r[1],
            "time_label": r[2],
            "price_cents": r[0].price_cents,
        }
        for r in slot_rows
    ]
    return {
        "item_count": len(slot_rows),
        "subtotal_cents": q.subtotal_cents,
        "member_discount_cents": q.member_discount_cents,
        "coupon_discount_cents": q.coupon_discount_cents,
        "points_used": q.points_used,
        "points_discount_cents": q.points_discount_cents,
        "total_cents": q.total_cents,
        "items": items,
        "max_usable_points": int(q.total_cents * get_settings().points_redeem_max_bp / 10000),
    }


@router.get("", summary="我的预约")
async def my_bookings(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    status: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, le=100),
) -> dict:
    q = select(Booking).where(Booking.user_id == user.id).order_by(Booking.id.desc())
    if status:
        q = q.where(Booking.status == status)
    total = await session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (await session.scalars(q.offset((page - 1) * size).limit(size))).all()
    # 一条 IN 查询取本页全部时段摘要，避免列表页 N+1
    item_map: dict[str, list[BookingItem]] = {}
    nos = [b.booking_no for b in rows]
    if nos:
        item_rows = (
            await session.scalars(select(BookingItem).where(BookingItem.booking_no.in_(nos)).order_by(BookingItem.id))
        ).all()
        for it in item_rows:
            item_map.setdefault(it.booking_no, []).append(it)
    return {
        "items": [serialize(b, items=item_map.get(b.booking_no, [])) for b in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/{booking_no}", summary="预约详情（仅本人，越权返回 404）")
async def booking_detail(
    booking_no: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    b = await get_for_user(session, user.id, booking_no)
    items: list[BookingItem] = list(
        (await session.scalars(select(BookingItem).where(BookingItem.booking_no == booking_no))).all()
    )
    return serialize(b, items=items)


@router.post("/{booking_no}/cancel", summary="取消预约（待支付直接取消；已支付开场前 2 小时前自动退款）")
async def cancel(
    booking_no: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return await cancel_by_user_with_refund(session, redis, user_id=user.id, booking_no=booking_no)
