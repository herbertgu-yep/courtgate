"""站内信：写 notifications 表即送达。默认启用，零外部依赖。"""

from __future__ import annotations

from typing import Any

from app.models import User
from app.services.notify.base import Notifier


class InboxNotifier(Notifier):
    channel = "inbox"

    async def send(self, user: User, template_code: str, context: dict[str, Any]) -> tuple[str, str]:
        return render(template_code, context)


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
    title = TEMPLATES[template_code][0]
    content = TEMPLATES[template_code][1].format(**ctx)
    return title, content
