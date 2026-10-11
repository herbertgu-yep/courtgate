"""管理端：场馆/场地/时段配置、放场、预约查询、经营统计（SQL 聚合）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_redis, get_session, require_operator
from app.models import Booking, BookingItem, Court, CourtSlot, User
from app.services import release_service

router = APIRouter(prefix="/api/admin", tags=["管理端"], dependencies=[Depends(require_operator)])


@router.get("/venues", summary="场馆列表")
async def list_venues(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.services import venue_service

    return await venue_service.list_venues(session)


@router.post("/venues", summary="创建场馆（含场地与营业配置）", status_code=201)
async def create_venue(body: dict, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.services import venue_service

    return await venue_service.create_venue(session, body)


@router.get("/venues/{venue_id}", summary="场馆详情（配置/场地/休息日/时段切片）")
async def venue_detail(venue_id: int, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.services import venue_service

    return await venue_service.venue_detail(session, venue_id)


@router.patch("/venues/{venue_id}", summary="编辑场馆（仅影响之后放场的批次）")
async def update_venue(venue_id: int, body: dict, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.services import venue_service

    return await venue_service.update_venue(session, venue_id, body)


@router.post("/venues/{venue_id}/closures/preview", summary="休息日预览（受影响预约清单）")
async def closure_preview(venue_id: int, body: dict, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from datetime import date as date_type

    from app.services import venue_service

    return await venue_service.closure_preview(
        session, venue_id, date_type.fromisoformat(str(body["closure_date"])[:10])
    )


@router.post("/venues/{venue_id}/closures", summary="设置休息日（确认后取消/退款并通知）")
async def apply_closure(
    body: dict,
    venue_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    operator: Annotated[User, Depends(require_operator)],
) -> dict:
    from app.services import venue_service

    return await venue_service.apply_closure(
        session,
        redis,
        venue_id=venue_id,
        closure_date=body["closure_date"],
        notify_content=body.get("notify_content") or None,
        force=bool(body.get("force", False)),
        created_by=operator.id,
    )


@router.get("/venues/{venue_id}/closures", summary="休息日列表")
async def list_closures(venue_id: int, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.services import venue_service

    return await venue_service.list_closures(session, venue_id)


@router.get("/venues/{venue_id}/bookings", summary="场馆预约查询（按日期筛选，含用户手机号）")
async def venue_bookings(
    venue_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    date: str | None = None,
    status: str | None = None,
) -> dict:
    from datetime import date as date_type

    court_ids = (await session.scalars(select(Court.id).where(Court.venue_id == venue_id))).all()
    q = (
        select(Booking)
        .distinct()
        .join(BookingItem, BookingItem.booking_no == Booking.booking_no)
        .where(BookingItem.court_id.in_(court_ids))
    )
    if date:
        q = q.where(BookingItem.slot_date == date_type.fromisoformat(date[:10]))
    if status:
        q = q.where(Booking.status == status)
    q = q.order_by(Booking.id.desc()).limit(100)
    rows = (await session.scalars(q)).all()
    nos = [b.booking_no for b in rows]
    items_map: dict[str, list] = {}
    if nos:
        for it in (
            await session.scalars(select(BookingItem).where(BookingItem.booking_no.in_(nos)).order_by(BookingItem.id))
        ).all():
            items_map.setdefault(it.booking_no, []).append(it)
    users = {u.id: u for u in (await session.scalars(select(User).where(User.id.in_([b.user_id for b in rows])))).all()}
    return {
        "items": [
            {
                "booking_no": b.booking_no,
                "user_nickname": users[b.user_id].nickname if b.user_id in users else "",
                "user_phone": users[b.user_id].phone_number if b.user_id in users else None,
                "status": b.status,
                "item_count": b.item_count,
                "total_cents": b.total_cents,
                "created_at": b.created_at,
                "items": [
                    {"court_name": i.court_name, "slot_date": str(i.slot_date), "time_label": i.time_label}
                    for i in items_map.get(b.booking_no, [])
                ],
            }
            for b in rows
        ]
    }


@router.patch("/courts/{court_id}", summary="编辑场地（名称/单价，仅影响之后放场的批次）")
async def update_court(court_id: int, body: dict, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.core.exceptions import NotFoundError

    c = await session.get(Court, court_id)
    if c is None:
        raise NotFoundError("场地不存在")
    if "name" in body:
        c.name = str(body["name"])[:50] or c.name
    if "base_price_cents" in body:
        price = int(body["base_price_cents"])
        if price < 100:
            from app.core.exceptions import CourtGateError

            e = CourtGateError("场地单价至少 1 元")
            e.code = "VALIDATION_ERROR"
            e.http_status = 422
            raise e
        c.base_price_cents = price
    await session.commit()
    return {"id": c.id, "name": c.name, "base_price_cents": c.base_price_cents}


@router.delete("/courts/{court_id}", summary="删除场地（停用：历史预约保留，不再参与之后放场）")
async def delete_court(court_id: int, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    c = await session.get(Court, court_id)
    if c is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("场地不存在")
    c.status = "inactive"
    await session.commit()
    return {"id": c.id, "name": c.name, "status": c.status}


@router.post("/courts", summary="创建场地（数量不限，管理员配置）", status_code=201)
async def create_court(body: dict, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    c = Court(
        venue_id=body["venue_id"],
        name=body["name"],
        court_type=body.get("court_type", ""),
        base_price_cents=body["base_price_cents"],
    )
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return {"id": c.id, "name": c.name, "base_price_cents": c.base_price_cents}


@router.post("/releases", summary="创建放场批次（批量生成可约单元）", status_code=201)
async def create_release(
    body: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
    operator: Annotated[User, Depends(require_operator)],
) -> dict:
    return await release_service.create_release(
        session,
        redis,
        venue_id=body["venue_id"],
        name=body["name"],
        period_start=body["period_start"],
        period_end=body["period_end"],
        open_at=body["open_at"],
        close_at=body["close_at"],
        per_user_limit=body.get("per_user_limit", 3),
        created_by=operator.id,
    )


@router.post("/releases/{release_id}/regenerate", summary="按当前场馆配置重生成批次时段（无预约记录时）")
async def regenerate_release(
    release_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    return await release_service.regenerate_release(session, redis, release_id)


@router.get("/coupon-templates", summary="券模板列表（库存与领取进度）")
async def list_coupon_templates(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.models import CouponTemplate

    rows = (await session.scalars(select(CouponTemplate).order_by(CouponTemplate.id.desc()))).all()
    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "type": t.type,
                "value": t.value,
                "min_spend_cents": t.min_spend_cents,
                "total_quantity": t.total_quantity,
                "claimed": t.claimed_count,
                "remaining": t.total_quantity - t.claimed_count,
                "per_user_limit": t.per_user_limit,
                "valid_from": str(t.valid_from),
                "valid_to": str(t.valid_to),
                "status": t.status,
            }
            for t in rows
        ]
    }


@router.patch("/coupons/{template_id}/status", summary="券模板停发/恢复")
async def set_coupon_status(
    template_id: int, body: dict, session: Annotated[AsyncSession, Depends(get_session)]
) -> dict:
    from app.models import CouponTemplate

    t = await session.get(CouponTemplate, template_id)
    if t is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("券模板不存在")
    status = str(body.get("status", ""))
    if status not in ("active", "inactive"):
        from app.core.exceptions import CourtGateError

        e = CourtGateError("状态仅支持 active / inactive")
        e.code = "VALIDATION_ERROR"
        e.http_status = 422
        raise e
    t.status = status
    await session.commit()
    return {"id": t.id, "status": t.status}


@router.post("/coupons", summary="创建券模板", status_code=201)
async def create_coupon(body: dict, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.models import CouponTemplate

    t = CouponTemplate(
        name=body["name"],
        type=body["type"],
        value=body["value"],
        min_spend_cents=body.get("min_spend_cents", 0),
        max_discount_cents=body.get("max_discount_cents", 0),
        total_quantity=body["total_quantity"],
        per_user_limit=body.get("per_user_limit", 1),
        valid_from=body["valid_from"],
        valid_to=body["valid_to"],
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    from app.cache.redis_client import get_async_redis
    from app.services import coupon_service

    await coupon_service.init_stock(get_async_redis(), t.id, t.total_quantity)
    return {"id": t.id, "name": t.name}


@router.post("/member-levels", summary="创建会员等级", status_code=201)
async def create_member_level(body: dict, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    from app.models import MemberLevel

    lv = MemberLevel(
        code=body["code"],
        name=body["name"],
        min_spent_cents=body["min_spent_cents"],
        discount_bp=body.get("discount_bp", 10000),
        points_rate_bp=body.get("points_rate_bp", 10000),
        sort_order=body.get("sort_order", 0),
    )
    session.add(lv)
    await session.commit()
    await session.refresh(lv)
    return {"id": lv.id, "code": lv.code}


@router.get("/bookings", summary="预约查询")
async def list_bookings(
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, le=100),
) -> dict:
    q = select(Booking).order_by(Booking.id.desc())
    if status:
        q = q.where(Booking.status == status)
    total = await session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (await session.scalars(q.offset((page - 1) * size).limit(size))).all()
    return {"items": [release_service_row(r) for r in rows], "total": total, "page": page, "size": size}


def release_service_row(b: Booking) -> dict:
    return {
        "booking_no": b.booking_no,
        "user_id": b.user_id,
        "status": b.status,
        "item_count": b.item_count,
        "total_cents": b.total_cents,
        "created_at": b.created_at,
        "expire_at": b.expire_at,
    }


@router.get("/stats/usage", summary="经营统计（SQL 聚合，不读全表进内存）")
async def stats_usage(
    session: Annotated[AsyncSession, Depends(get_session)],
    release_id: int | None = None,
) -> dict:
    q = select(
        CourtSlot.court_id,
        func.count().label("slots_total"),
        func.sum(func.if_(CourtSlot.status == "booked", 1, 0)).label("slots_booked"),
    ).group_by(CourtSlot.court_id)
    if release_id:
        q = q.where(CourtSlot.release_id == release_id)
    rows = (await session.execute(q)).all()
    revenue = await session.scalar(
        select(func.coalesce(func.sum(Booking.total_cents), 0)).where(Booking.status == "paid")
    )
    return {
        "items": [
            {
                "court_id": r.court_id,
                "slots_total": r.slots_total,
                "slots_booked": r.slots_booked or 0,
                "utilization_rate": round((r.slots_booked or 0) / r.slots_total, 3) if r.slots_total else 0,
            }
            for r in rows
        ],
        "revenue_cents": revenue or 0,
    }
