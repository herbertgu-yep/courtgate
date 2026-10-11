"""支付单创建与回调处理：验签 + 幂等 + CAS 状态推进。"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BookingStateInvalidError, NotFoundError, PaymentSignatureInvalidError
from app.core.logging import get_logger
from app.core.metrics import payment_callback_total, points_earned_total
from app.models import Booking, Payment, User
from app.services.payment.registry import get_channel

log = get_logger("courtgate.payment")


def gen_payment_no(booking_no: str) -> str:
    import secrets

    return f"PAY{booking_no}{secrets.randbelow(100):02d}"


async def create_payment(session: AsyncSession, *, booking_no: str, channel: str, user_id: int) -> dict:
    """为预约单创建支付单；重复创建返回同一支付单。"""
    booking = await session.scalar(select(Booking).where(Booking.booking_no == booking_no))
    if booking is None or booking.user_id != user_id:
        raise NotFoundError("预约单不存在")
    if booking.status != "pending_paid":
        raise BookingStateInvalidError(details={"status": booking.status})

    existing = await session.scalar(
        select(Payment).where(Payment.booking_id == booking.id, Payment.status == "pending", Payment.channel == channel)
    )
    ch = get_channel(channel)
    if existing is None:
        payment = Payment(
            payment_no=gen_payment_no(booking_no),
            booking_id=booking.id,
            amount_cents=booking.total_cents,
            channel=channel,
            status="pending",
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        pno = payment.payment_no
    else:
        pno = existing.payment_no
    intent = await ch.create_payment(booking_no, booking.total_cents)
    return {"payment_no": pno, "amount_cents": booking.total_cents, **intent}


async def handle_callback(session: AsyncSession, *, channel: str, payload: dict[str, Any]) -> dict:
    """回调处理：验签 → 幂等 → CAS。已处理过的回调一律返回 200。"""
    ch = get_channel(channel)
    try:
        data = ch.verify_callback(payload)
    except PaymentSignatureInvalidError:
        payment_callback_total.labels(channel=channel, result="invalid").inc()
        raise

    # 幂等：同渠道同第三方流水号已成功 → 直接 200
    dup = await session.scalar(
        select(Payment).where(
            Payment.channel == channel, Payment.third_party_no == data.third_party_no, Payment.status == "success"
        )
    )
    if dup is not None:
        payment_callback_total.labels(channel=channel, result="duplicate").inc()
        return {"received": True}

    payment = await session.scalar(select(Payment).where(Payment.payment_no == data.payment_no))
    if payment is None:
        raise NotFoundError("支付单不存在")
    if data.amount_cents != payment.amount_cents:
        raise PaymentSignatureInvalidError("回调金额与支付单不一致")

    import datetime as dt

    now_iso = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")

    res: CursorResult = await session.execute(  # type: ignore[assignment]
        update(Payment)
        .where(Payment.payment_no == data.payment_no, Payment.status == "pending")
        .values(
            status="success",
            paid_at=now_iso,
            third_party_no=data.third_party_no,
            callback_payload=json.dumps(payload, ensure_ascii=False),
        )
    )
    if res.rowcount != 1:
        await session.rollback()
        payment_callback_total.labels(channel=channel, result="duplicate").inc()
        return {"received": True}  # 已被并发处理

    res2: CursorResult = await session.execute(  # type: ignore[assignment]
        update(Booking)
        .where(Booking.id == payment.booking_id, Booking.status == "pending_paid")
        .values(status="paid", paid_at=now_iso)
    )
    await session.commit()
    if res2.rowcount != 1:
        # 已被超时取消：钱已收但预约被取消，真实场景需要退款流程（本项目不做，记录日志）
        log.error("paid_but_not_pending", payment_no=data.payment_no, booking_id=payment.booking_id)
    else:
        # Phase B 入账：累计消费 → 会员升级 → 赠送积分（均幂等）
        from app.services import member_service, points_service

        booking = await session.scalar(select(Booking).where(Booking.id == payment.booking_id))
        assert booking is not None  # 刚置为 paid，必然存在
        user = await session.get(User, booking.user_id)
        assert user is not None
        user.total_spent_cents += booking.total_cents
        upgraded = await member_service.sync_user_level(session, user)
        level = await member_service.level_for(session, user.member_level)
        rate_bp = level.points_rate_bp if level else 10000
        earn = points_service.earn_amount(booking.total_cents, rate_bp)
        if earn > 0:
            earned = await points_service.record(
                session,
                user_id=user.id,
                change_type="earn",
                points=earn,
                ref_booking_no=booking.booking_no,
                remark="支付赠送",
            )
            if earned:
                points_earned_total.inc()
        await session.commit()
        if upgraded:
            log.info("member_upgraded", user_id=user.id, level=user.member_level)
        paid_ctx = {"booking_no": booking.booking_no, "amount_yuan": f"{booking.total_cents / 100:.2f}"}
        try:
            from app.services.booking_service import _write_inbox

            await _write_inbox(session, user.id, "BOOKING_PAID", booking.booking_no, paid_ctx)
        except Exception:  # noqa: BLE001
            log.error("inbox_write_failed", booking_no=booking.booking_no)
        try:
            from app.tasks.notify_tasks import send_notifications

            send_notifications.delay(
                user.id, "BOOKING_PAID", "booking", booking.booking_no, json.dumps(paid_ctx, ensure_ascii=False)
            )
        except Exception:  # noqa: BLE001
            pass
    payment_callback_total.labels(channel=channel, result="ok").inc()
    log.info("payment_callback_received", payment_no=data.payment_no, is_duplicate=False)
    return {"received": True}


def build_mock_callback(
    payment_no: str, amount_cents: int, *, secret: str, third_party_no: str | None = None, ts: int | None = None
) -> dict:
    """构造一个合法的 Mock 回调（演示/测试用）。"""
    import secrets

    from app.services.payment.base import sign_payload

    tp = third_party_no or f"MOCK-{secrets.token_hex(4).upper()}"
    t = ts or int(time.time())
    sig = sign_payload([payment_no, tp, amount_cents, "success", t], secret)
    return {
        "payment_no": payment_no,
        "third_party_no": tp,
        "amount_cents": amount_cents,
        "status": "success",
        "timestamp": t,
        "signature": sig,
    }
