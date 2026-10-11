"""通知服务：幂等落库 + 渠道分发 + 重试计数。业务代码只调 dispatch。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Notification

log = get_logger("courtgate.notify")

TEMPLATES = {
    "BOOKING_CREATED": ("预约成功", "您已预约 {items}，请在 {expire_at} 前完成支付，超时将自动释放。"),
    "BOOKING_PAID": ("支付成功", "预约 {booking_no} 已支付，实付 {amount_yuan} 元。"),
    "BOOKING_CANCELLED": ("预约已取消", "预约 {booking_no} 已取消（{reason}），时段已释放。"),
    "COUPON_CLAIMED": ("领券成功", "您已领取「{name}」，可在下单时使用。"),
    "SYSTEM_ALERT": (
        "系统告警",
        "{content}",
    ),
    "VENUE_CLOSURE": (
        "场馆闭馆通知",
        "由于场馆原因，{date} {venue_name} 闭馆，您的预约 {booking_no} {action}。{custom}",
    ),
}


def render(template_code: str, ctx: dict[str, Any]) -> tuple[str, str]:
    title, content = TEMPLATES[template_code]
    return title, content.format(**ctx)


async def record(
    session: AsyncSession,
    *,
    user_id: int,
    channel: str,
    template_code: str,
    title: str,
    content: str,
    ref_type: str,
    ref_id: str,
) -> Notification:
    """幂等落库：同 (channel, template_code, ref_id) 只写一条。"""
    dup = await session.scalar(
        select(Notification).where(
            Notification.channel == channel, Notification.template_code == template_code, Notification.ref_id == ref_id
        )
    )
    if dup is not None:
        return dup
    n = Notification(
        user_id=user_id,
        channel=channel,
        template_code=template_code,
        title=title,
        content=content,
        status="pending",
        ref_type=ref_type,
        ref_id=ref_id,
    )
    session.add(n)
    return n
