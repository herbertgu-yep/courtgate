"""预约：幂等提交、原子占用（Redis）/朴素占用（DB）双路径、状态机、超时取消。"""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import keys
from app.core.config import get_settings
from app.core.exceptions import (
    BookingStateInvalidError,
    CouponNotApplicableError,
    CourtGateError,
    IdempotencyConflictError,
    InsufficientPointsError,
    NotFoundError,
    PerUserLimitExceededError,
    SlotUnavailableError,
)
from app.core.logging import get_logger
from app.core.metrics import bookings_cancelled_total, bookings_created_total, slots_occupied_total
from app.models import (
    Booking,
    BookingItem,
    CouponTemplate,
    Court,
    CourtSlot,
    PointsLedger,
    StockFlow,
    TimeSlot,
    User,
    UserCoupon,
    Venue,
)
from app.services import release_service, slot_service

log = get_logger("courtgate.booking")


def gen_booking_no(user_id: int) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{ts}{secrets.randbelow(10**6):06d}{user_id % 10000:04d}"


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _write_inbox(session: AsyncSession, user_id: int, template_code: str, ref_id: str, ctx: dict) -> None:
    """站内信同事务直写：用户登录即见，不依赖 Celery worker。幂等：同 (channel, template, ref_id) 一条。"""
    from app.models import Notification
    from app.services.notify_service import render

    dup = await session.scalar(
        select(Notification).where(
            Notification.channel == "inbox",
            Notification.template_code == template_code,
            Notification.ref_id == ref_id,
        )
    )
    if dup is not None:
        return
    title, content = render(template_code, ctx)
    session.add(
        Notification(
            user_id=user_id,
            channel="inbox",
            template_code=template_code,
            title=title,
            content=content,
            status="sent",
            ref_type="booking",
            ref_id=ref_id,
        )
    )


def _dispatch_notify(user_id: int, template_code: str, *, ref_id: str, ctx: dict) -> None:
    """外部渠道（email/sms）投递在主事务提交之后；失败不影响主流程。"""
    try:
        from app.tasks.notify_tasks import send_notifications

        send_notifications.delay(
            user_id, template_code, "booking", ref_id, json.dumps(ctx, ensure_ascii=False, default=str)
        )
    except Exception:  # noqa: BLE001
        log.error("notify_dispatch_failed", template=template_code, ref_id=ref_id)


# ---------------------------------------------------------------- 创建预约


async def create_booking(
    session: AsyncSession,
    redis: Redis,
    *,
    user_id: int,
    release_id: int,
    court_slot_ids: list[int],
    idempotency_key: str,
    coupon_id: int | None = None,
    use_points: int = 0,
) -> dict:
    """幂等创建预约。use_redis_claim=False 时走朴素 DB 路径（用于对比与教学）。"""
    idem_key = keys.idem(user_id, idempotency_key)
    existing = await redis.get(idem_key)
    if existing and existing != "processing":
        booking = await _get_by_no(session, existing)
        if booking is not None:
            return serialize(booking)
        await redis.delete(idem_key)  # 失效标记放行重试
        existing = None
    if existing == "processing":
        raise IdempotencyConflictError()

    ok = await redis.set(idem_key, "processing", nx=True, ex=24 * 3600)
    if not ok:
        val = await redis.get(idem_key)
        if val and val != "processing":
            booking = await _get_by_no(session, val)
            if booking is not None:
                return serialize(booking)
        raise IdempotencyConflictError()

    try:
        result = await _create(
            session,
            redis,
            user_id=user_id,
            release_id=release_id,
            court_slot_ids=court_slot_ids,
            idempotency_key=idempotency_key,
            coupon_id=coupon_id,
            use_points=use_points,
        )
    except Exception:
        val = await redis.get(idem_key)
        if val == "processing":
            await redis.delete(idem_key)
        raise
    await redis.set(idem_key, result["booking_no"], ex=24 * 3600)
    return result


def _use_redis_claim() -> bool:
    import os

    return os.environ.get("COURTGATE_USE_REDIS_CLAIM", "1") == "1"


async def _create(
    session: AsyncSession,
    redis: Redis,
    *,
    user_id: int,
    release_id: int,
    court_slot_ids: list[int],
    idempotency_key: str,
    coupon_id: int | None = None,
    use_points: int = 0,
) -> dict:
    s = get_settings()
    if not court_slot_ids or len(court_slot_ids) > s.max_slots_per_booking:
        raise CourtGateError(f"一次预约的时段数量须在 1~{s.max_slots_per_booking} 之间")

    release = await release_service.ensure_open(session, release_id)

    slots = (
        await session.scalars(
            select(CourtSlot).where(CourtSlot.id.in_(court_slot_ids), CourtSlot.release_id == release_id)
        )
    ).all()
    if len(slots) != len(set(court_slot_ids)):
        raise NotFoundError("部分时段不存在或不属于该批次")
    not_free = [c.id for c in slots if c.status != "free"]
    if not_free:
        raise SlotUnavailableError(details={"court_slot_ids": not_free})
    # 闭馆校验：休息日的时段不可预约
    from app.services import venue_service

    await venue_service.assert_dates_open(session, release.venue_id, {c.slot_date for c in slots})

    subtotal = sum(c.price_cents for c in slots)
    # 定价引擎（纯函数）：会员折扣 → 优惠券 → 积分，顺序固定
    from app.services import member_service, points_service
    from app.services.pricing.engine import CouponView, quote

    user = await session.get(User, user_id)
    assert user is not None
    level = await member_service.level_for(session, user.member_level)
    member_bp = level.discount_bp if level else 10000
    coupon_view = None
    if coupon_id is not None:
        coupon_row = await session.get(UserCoupon, coupon_id)
        if coupon_row is None or coupon_row.user_id != user_id or coupon_row.status != "unused":
            raise CouponNotApplicableError(details={"coupon_id": coupon_id})
        ct = await session.get(CouponTemplate, coupon_row.template_id)
        assert ct is not None
        coupon_view = CouponView(
            type=ct.type, value=ct.value, min_spend_cents=ct.min_spend_cents, max_discount_cents=ct.max_discount_cents
        )
    q = quote(
        subtotal_cents=subtotal,
        member_discount_bp=member_bp,
        coupon=coupon_view,
        use_points=use_points,
        user_points=user.points_balance,
        points_redeem_max_bp=get_settings().points_redeem_max_bp,
    )

    # 占用：Redis 原子抢占（或朴素路径）
    if _use_redis_claim():
        await slot_service.claim(
            redis,
            release_id=release_id,
            user_id=user_id,
            slot_ids=court_slot_ids,
            per_user_limit=release.per_user_limit,
            session=session,
        )
    else:
        await _naive_check_limit(
            session,
            user_id=user_id,
            release_id=release_id,
            quantity=len(court_slot_ids),
            per_user_limit=release.per_user_limit,
        )

    # 锁积分（CAS）：余额不足直接拒绝（券核销在事务内，随整体回滚）
    if use_points > 0:
        res_p: CursorResult = await session.execute(  # type: ignore[assignment]
            update(User)
            .where(User.id == user_id, User.points_balance >= use_points)
            .values(points_balance=User.points_balance - use_points)
        )
        if res_p.rowcount != 1:
            raise InsufficientPointsError(details={"use_points": use_points})

    booking_no = gen_booking_no(user_id)
    expire_at = _iso(_utcnow() + timedelta(seconds=s.booking_expire_seconds))
    venue = await session.get(Venue, release.venue_id)
    court_names = {
        c.id: c.name
        for c in (await session.scalars(select(Court).where(Court.id.in_({c.court_id for c in slots})))).all()
    }
    ts_labels = {
        t.id: t.label
        for t in (await session.scalars(select(TimeSlot).where(TimeSlot.id.in_({c.time_slot_id for c in slots})))).all()
    }

    try:
        # CAS 占用：带 status='free' 条件，affected_rows 必须等于数量
        res: CursorResult = await session.execute(  # type: ignore[assignment]
            update(CourtSlot)
            .where(CourtSlot.id.in_(court_slot_ids), CourtSlot.status == "free")
            .values(status="booked", booking_no=booking_no)
        )
        if res.rowcount != len(court_slot_ids):
            raise SlotUnavailableError(details={"court_slot_ids": court_slot_ids})

        booking = Booking(
            booking_no=booking_no,
            user_id=user_id,
            venue_id=release.venue_id,
            release_id=release_id,
            item_count=len(slots),
            subtotal_cents=q.subtotal_cents,
            member_discount_cents=q.member_discount_cents,
            coupon_id=coupon_id,
            coupon_discount_cents=q.coupon_discount_cents,
            points_used=q.points_used,
            points_discount_cents=q.points_discount_cents,
            total_cents=q.total_cents,
            status="pending_paid",
            idempotency_key=idempotency_key,
            expire_at=expire_at,
        )
        session.add(booking)
        await session.flush()
        for c in slots:
            session.add(
                BookingItem(
                    booking_no=booking_no,
                    court_slot_id=c.id,
                    court_id=c.court_id,
                    court_name=court_names.get(c.court_id, ""),
                    venue_name=venue.name if venue else "",
                    slot_date=c.slot_date,
                    time_label=ts_labels.get(c.time_slot_id, ""),
                    price_cents=c.price_cents,
                )
            )
        session.add(StockFlow(booking_no=booking_no, release_id=release_id, change_type="occupy", quantity=len(slots)))
        # 券核销 + 积分抵扣流水（同一事务，随整体回滚）
        if coupon_id is not None:
            res_c: CursorResult = await session.execute(  # type: ignore[assignment]
                update(UserCoupon)
                .where(UserCoupon.id == coupon_id, UserCoupon.status == "unused")
                .values(status="used", booking_no=booking_no)
            )
            if res_c.rowcount != 1:
                raise CouponNotApplicableError(details={"coupon_id": coupon_id})
        if q.points_used > 0:
            await points_service.record(
                session,
                user_id=user_id,
                change_type="redeem",
                points=-q.points_used,
                ref_booking_no=booking_no,
                remark="预约抵扣",
            )
        await session.commit()
    except Exception:
        await session.rollback()
        if _use_redis_claim():
            try:
                await slot_service.release(redis, release_id=release_id, user_id=user_id, slot_ids=court_slot_ids)
            except Exception:  # noqa: BLE001
                log.error("redis_release_rollback_failed", booking_no=booking_no)
        raise

    bookings_created_total.labels(venue_id=str(release.venue_id)).inc()
    slots_occupied_total.inc(len(slots))
    log.info(
        "booking_created",
        booking_no=booking_no,
        user_id=user_id,
        release_id=release_id,
        item_count=len(slots),
        total_cents=q.total_cents,
    )

    created_ctx = {"items": "、".join(ts_labels.get(c.time_slot_id, "") for c in slots), "expire_at": expire_at}
    await _write_inbox(session, user_id, "BOOKING_CREATED", booking_no, created_ctx)
    _dispatch_notify(user_id, "BOOKING_CREATED", ref_id=booking_no, ctx=created_ctx)

    try:
        from app.tasks import booking_tasks

        booking_tasks.cancel_expired_booking.apply_async((booking_no,), eta=expire_at)
    except Exception:  # noqa: BLE001
        pass

    fresh = await _get_by_no(session, booking_no)
    if fresh is None:  # pragma: no cover
        raise NotFoundError("预约单创建后查询失败")
    return serialize(fresh)


async def _naive_check_limit(
    session: AsyncSession, *, user_id: int, release_id: int, quantity: int, per_user_limit: int
) -> None:
    """朴素限购：先查已购数再判断。并发下会放过超额（教学用）。"""
    from sqlalchemy import func

    booked = (
        await session.scalar(
            select(func.coalesce(func.sum(StockFlow.quantity), 0)).where(
                StockFlow.release_id == release_id,
                StockFlow.change_type == "occupy",
                StockFlow.booking_no.in_(
                    select(Booking.booking_no).where(
                        Booking.user_id == user_id,
                        Booking.release_id == release_id,
                        Booking.status.in_(("pending_paid", "paid")),
                    )
                ),
            )
        )
        or 0
    )
    if booked + quantity > per_user_limit:
        raise PerUserLimitExceededError(details={"per_user_limit": per_user_limit})


# ---------------------------------------------------------------- 查询 / 取消


async def _get_by_no(session: AsyncSession, booking_no: str) -> Booking | None:
    return await session.scalar(select(Booking).where(Booking.booking_no == booking_no))


async def get_for_user(session: AsyncSession, user_id: int, booking_no: str) -> Booking:
    booking = await _get_by_no(session, booking_no)
    if booking is None or booking.user_id != user_id:
        raise NotFoundError("预约单不存在")  # 越权一律 404，不泄露存在性
    return booking


async def cancel_by_user(session: AsyncSession, redis: Redis, *, user_id: int, booking_no: str) -> dict:
    booking = await get_for_user(session, user_id, booking_no)
    if booking.status != "pending_paid":
        raise BookingStateInvalidError(details={"status": booking.status})
    res: CursorResult = await session.execute(  # type: ignore[assignment]
        update(Booking)
        .where(Booking.booking_no == booking_no, Booking.status == "pending_paid")
        .values(status="cancelled", cancelled_at=_iso(_utcnow()), cancel_reason="user")
    )
    if res.rowcount != 1:
        await session.rollback()
        raise BookingStateInvalidError(details={"status": "changed"})
    await _release_slots(session, redis, booking)
    # 释放券与返还积分（均幂等）
    from app.services import coupon_service, points_service

    coupon_id = await coupon_service.release(session, booking_no=booking_no)
    if coupon_id is not None:
        log.info("coupon_released", booking_no=booking_no, coupon_id=coupon_id)
    if booking.points_used > 0:
        await points_service.record(
            session,
            user_id=booking.user_id,
            change_type="refund",
            points=booking.points_used,
            ref_booking_no=booking_no,
            remark="取消返还",
        )
    bookings_cancelled_total.labels(reason="user").inc()
    await session.commit()
    cancel_ctx = {"booking_no": booking_no, "reason": "用户取消"}
    await _write_inbox(session, user_id, "BOOKING_CANCELLED", booking_no, cancel_ctx)
    _dispatch_notify(user_id, "BOOKING_CANCELLED", ref_id=booking_no, ctx=cancel_ctx)
    fresh = await _get_by_no(session, booking_no)
    if fresh is None:  # pragma: no cover
        raise NotFoundError("预约单不存在")
    return serialize(fresh)


async def _release_slots(session: AsyncSession, redis: Redis, booking: Booking) -> None:
    """归还已占用单元（数据库 + Redis），写 release 流水（唯一约束防重复归还）。"""
    items = (await session.scalars(select(BookingItem).where(BookingItem.booking_no == booking.booking_no))).all()
    slot_ids = [i.court_slot_id for i in items if i.court_slot_id is not None]
    if slot_ids:
        await session.execute(
            update(CourtSlot)
            .where(CourtSlot.id.in_(slot_ids), CourtSlot.booking_no == booking.booking_no, CourtSlot.status == "booked")
            .values(status="free", booking_no="")
        )
    session.add(
        StockFlow(
            booking_no=booking.booking_no, release_id=booking.release_id, change_type="release", quantity=len(slot_ids)
        )
    )
    try:
        await slot_service.release(redis, release_id=booking.release_id, user_id=booking.user_id, slot_ids=slot_ids)
    except Exception:  # noqa: BLE001
        log.error("redis_release_failed", booking_no=booking.booking_no)


async def close_booking_for_closure(session: AsyncSession, redis: Redis, booking: Booking) -> str:
    """闭馆场景处理单笔预约：待支付→取消，已支付→退款。不提交事务（由调用方统一提交）。

    返回 "cancelled" / "refunded"。时段归还、优惠券返还、赠送积分扣回、
    款项原路退回（沙箱渠道即时代退，真实渠道未接入则标记待人工）。
    """
    if booking.status == "pending_paid":
        await _cancel_pending_booking(session, redis, booking, cancel_reason="closure", points_remark="闭馆返还")
        bookings_cancelled_total.labels(reason="closure").inc()
        return "cancelled"
    if booking.status == "paid":
        await _refund_paid_booking(
            session, redis, booking, cancel_reason="closure_refund", points_remark="闭馆退款扣回"
        )
        return "refunded"
    raise BookingStateInvalidError(details={"status": booking.status})


async def _cancel_pending_booking(
    session: AsyncSession, redis: Redis, booking: Booking, *, cancel_reason: str, points_remark: str
) -> None:
    """取消待支付单：CAS 置取消、归还时段、退券、退积分。不提交事务。"""
    from app.services import coupon_service, points_service

    res: CursorResult = await session.execute(  # type: ignore[assignment]
        update(Booking)
        .where(Booking.booking_no == booking.booking_no, Booking.status == "pending_paid")
        .values(status="cancelled", cancelled_at=_iso(_utcnow()), cancel_reason=cancel_reason)
    )
    if res.rowcount != 1:
        raise BookingStateInvalidError(details={"status": "changed"})
    await _release_slots(session, redis, booking)
    # 历史预约项与时段解绑：唯一约束只约束当前有效占用，展示字段已冗余
    await session.execute(
        update(BookingItem).where(BookingItem.booking_no == booking.booking_no).values(court_slot_id=None)
    )
    coupon_id = await coupon_service.release(session, booking_no=booking.booking_no)
    if coupon_id is not None:
        log.info("coupon_released", booking_no=booking.booking_no, coupon_id=coupon_id)
    if booking.points_used > 0:
        await points_service.record(
            session,
            user_id=booking.user_id,
            change_type="refund",
            points=booking.points_used,
            ref_booking_no=booking.booking_no,
            remark=points_remark,
        )


async def _refund_paid_booking(
    session: AsyncSession, redis: Redis, booking: Booking, *, cancel_reason: str, points_remark: str
) -> None:
    """已支付单退款：CAS 置退款、归还时段、退券、扣回赠送积分、扣减累计消费、支付原路退。不提交事务。"""
    from app.services import coupon_service, points_service

    res_paid: CursorResult = await session.execute(  # type: ignore[assignment]
        update(Booking)
        .where(Booking.booking_no == booking.booking_no, Booking.status == "paid")
        .values(status="refunded", cancelled_at=_iso(_utcnow()), cancel_reason=cancel_reason)
    )
    if res_paid.rowcount != 1:
        raise BookingStateInvalidError(details={"status": "changed"})
    await _release_slots(session, redis, booking)
    await session.execute(
        update(BookingItem).where(BookingItem.booking_no == booking.booking_no).values(court_slot_id=None)
    )
    coupon_id = await coupon_service.release(session, booking_no=booking.booking_no)
    if coupon_id is not None:
        log.info("coupon_released_on_refund", booking_no=booking.booking_no, coupon_id=coupon_id)
    user = await session.get(User, booking.user_id)
    assert user is not None
    # 扣回支付时赠送的积分（余额不足则扣到 0 为止）
    earn = await session.scalar(
        select(PointsLedger).where(
            PointsLedger.ref_booking_no == booking.booking_no, PointsLedger.change_type == "earn"
        )
    )
    if earn is not None and earn.points > 0:
        deduct = min(earn.points, user.points_balance)
        if deduct > 0:
            await points_service.record(
                session,
                user_id=user.id,
                change_type="closure_deduct",
                points=-deduct,
                ref_booking_no=booking.booking_no,
                remark=points_remark,
            )
    # 累计消费同步扣减，会员等级随之重算
    user.total_spent_cents = max(0, user.total_spent_cents - booking.total_cents)
    from app.services import member_service

    await member_service.sync_user_level(session, user)
    await _refund_payment(session, booking)


FREE_CANCEL_BEFORE_MINUTES = 120  # 开场前 2 小时内不可取消已支付预约


def _earliest_slot_start_utc(items: list[BookingItem]) -> datetime | None:
    """预约时段最早开始时刻（场地时间为东八区）。"""
    from datetime import timedelta, timezone

    cst = timezone(timedelta(hours=8))
    starts = []
    for i in items:
        try:
            hh, mm = i.time_label.split("-")[0].split(":")
            starts.append(datetime.combine(i.slot_date, datetime.min.time()).replace(hour=int(hh), minute=int(mm)))
        except (ValueError, IndexError):
            continue
    if not starts:
        return None
    return min(starts).replace(tzinfo=cst).astimezone(UTC)


async def cancel_by_user_with_refund(session: AsyncSession, redis: Redis, *, user_id: int, booking_no: str) -> dict:
    """用户取消：待支付直接取消；已支付仅限开场前 2 小时之前，自动原路退款。"""
    booking = await get_for_user(session, user_id, booking_no)
    if booking.status == "paid":
        items = list(await session.scalars(select(BookingItem).where(BookingItem.booking_no == booking_no)))
        start = _earliest_slot_start_utc(items)
        if start is not None and start - _utcnow() < timedelta(minutes=FREE_CANCEL_BEFORE_MINUTES):
            from app.core.exceptions import CourtGateError

            e = CourtGateError("开场前 2 小时内不可取消，时段起算时间临近")
            e.code = "CANCEL_WINDOW"
            e.http_status = 409
            raise e
        await _refund_paid_booking(
            session, redis, booking, cancel_reason="user_refund", points_remark="用户取消退款扣回"
        )
        bookings_cancelled_total.labels(reason="user_refund").inc()  # noqa: E501
        await session.commit()
        cancel_ctx = {"booking_no": booking_no, "reason": "用户取消，款项已原路退回"}
        await _write_inbox(session, user_id, "BOOKING_CANCELLED", booking_no, cancel_ctx)
        _dispatch_notify(user_id, "BOOKING_CANCELLED", ref_id=booking_no, ctx=cancel_ctx)
        fresh = await _get_by_no(session, booking_no)
        assert fresh is not None  # 刚更新过
        return serialize(fresh)
    return await cancel_by_user(session, redis, user_id=user_id, booking_no=booking_no)


async def _refund_payment(session: AsyncSession, booking: Booking) -> None:
    """支付单置为已退款；沙箱渠道即时代退，真实渠道未接入则留待人工。"""
    from app.models import Payment
    from app.services.payment.registry import get_channel

    payment = await session.scalar(
        select(Payment).where(Payment.booking_id == booking.id, Payment.status == "paid").order_by(Payment.id.desc())
    )
    if payment is None:
        return
    res: CursorResult = await session.execute(  # type: ignore[assignment]
        update(Payment).where(Payment.id == payment.id, Payment.status == "paid").values(status="refunded")
    )
    if res.rowcount != 1:
        return
    try:
        channel = get_channel(payment.channel)
        result = await channel.refund(payment.payment_no, payment.amount_cents)
        log.info("refund_channel_ok", payment_no=payment.payment_no, result=result)
    except NotImplementedError:
        log.warning("refund_channel_not_implemented", channel=payment.channel, payment_no=payment.payment_no)
    except Exception:  # noqa: BLE001
        log.error("refund_channel_failed", channel=payment.channel, payment_no=payment.payment_no)


async def dispatch_closure_notice(
    session: AsyncSession, booking: Booking, *, venue_name: str, date: str, action: str, custom: str | None
) -> None:
    """闭馆通知：一笔预约一条，站内信同事务直写；馆方自定义留言可选，缺省用默认致歉文案。"""
    ctx = {
        "venue_name": venue_name,
        "date": date,
        "booking_no": booking.booking_no,
        "action": "已自动取消，时段已释放" if action == "cancelled" else "已进入退款流程，款项将原路退回",
        "custom": f"馆方留言：{custom}" if custom else "给您带来不便深表歉意。",
    }
    await _write_inbox(session, booking.user_id, "VENUE_CLOSURE", booking.booking_no, ctx)
    _dispatch_notify(booking.user_id, "VENUE_CLOSURE", ref_id=booking.booking_no, ctx=ctx)


# ---------------------------------------------------------------- 序列化


def serialize(b: Booking, items: list[BookingItem] | None = None) -> dict:
    out = {
        "booking_no": b.booking_no,
        "status": b.status,
        "item_count": b.item_count,
        "subtotal_cents": b.subtotal_cents,
        "member_discount_cents": b.member_discount_cents,
        "coupon_discount_cents": b.coupon_discount_cents,
        "points_used": b.points_used,
        "points_discount_cents": b.points_discount_cents,
        "total_cents": b.total_cents,
        "expire_at": b.expire_at,
        "created_at": b.created_at,
    }
    if items is not None:
        out["items"] = [
            {
                "court_slot_id": i.court_slot_id,
                "venue_name": i.venue_name,
                "court_name": i.court_name,
                "slot_date": str(i.slot_date),
                "time_label": i.time_label,
                "price_cents": i.price_cents,
            }
            for i in items
        ]
    return out
