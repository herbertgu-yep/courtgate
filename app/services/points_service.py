"""积分：账本为权威，余额为冗余。所有变动幂等（唯一约束兜底）。"""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CourtGateError
from app.core.logging import get_logger
from app.core.money import bp_multiply
from app.models import PointsLedger, User

log = get_logger("courtgate.points")


def earn_amount(total_cents: int, points_rate_bp: int) -> int:
    """支付赠送积分：实付 × 倍率 / 10000（默认 1 元 = 1 积分）。"""
    return bp_multiply(total_cents, points_rate_bp)


async def record(
    session: AsyncSession,
    *,
    user_id: int,
    change_type: str,
    points: int,
    ref_booking_no: str = "",
    remark: str = "",
) -> int:
    """写一条积分流水并更新余额。同 (ref_booking_no, change_type) 只入账一次。

    返回实际入账的积分（重复调用返回 0）。
    """
    user = await session.get(User, user_id)
    if user is None:
        raise CourtGateError("用户不存在")
    if ref_booking_no:
        dup = await session.scalar(
            select(PointsLedger).where(
                PointsLedger.ref_booking_no == ref_booking_no, PointsLedger.change_type == change_type
            )
        )
        if dup is not None:
            return 0
    balance_after = user.points_balance + points
    ledger = PointsLedger(
        user_id=user_id,
        change_type=change_type,
        points=points,
        balance_after=balance_after,
        ref_booking_no=ref_booking_no,
        remark=remark,
    )
    session.add(ledger)
    await session.execute(
        update(User)
        .where(User.id == user_id, User.points_balance >= -points)
        .values(points_balance=user.points_balance + points)
    )
    return points
