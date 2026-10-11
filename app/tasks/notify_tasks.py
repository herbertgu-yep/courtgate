"""异步通知：幂等落库 → 渠道分发 → 失败重试（指数退避，最多 3 次）。

业务侧只投递 send_notifications(user_id, template_code, ref_type, ref_id, ctx)；
inbox 站内信 + email / sms 外部渠道统一在此落库后分发。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models import Notification, User
from app.tasks.celery_app import celery_app

log = get_logger("courtgate.task.notify")


@celery_app.task(
    name="app.tasks.notify_tasks.send_notifications", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def send_notifications(user_id: int, template_code: str, ref_type: str, ref_id: str, ctx_json: str = "{}") -> dict:
    """对每个启用的外部渠道（email/sms）幂等落库并发送。"""
    ctx = json.loads(ctx_json)
    session = get_sync_session()
    out: dict = {}
    try:
        from app.services.notify.registry import get_notifier
        from app.services.notify_service import render

        for channel in ("inbox", "email", "sms"):
            n = session.scalar(
                select(Notification).where(
                    Notification.channel == channel,
                    Notification.template_code == template_code,
                    Notification.ref_id == ref_id,
                )
            )
            if n is not None and n.status == "sent":
                out[channel] = "already_sent"
                continue
            user = session.get(User, user_id)
            notifier = get_notifier(channel)
            if notifier is None or user is None:
                continue
            if hasattr(notifier, "enabled") and not notifier.enabled():
                out[channel] = "channel_disabled"
                continue
            title, content = render(template_code, ctx)
            if n is None:
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
                session.commit()
                session.refresh(n)
            try:
                asyncio.run(notifier.send(user, template_code, ctx))
                n.status, n.sent_at = "sent", dt.datetime.now(dt.UTC)
                session.commit()
                from app.core.metrics import notifications_total

                notifications_total.labels(channel=channel, status="sent").inc()
                out[channel] = "sent"
            except Exception as e:  # noqa: BLE001
                n.retry_count = n.retry_count + 1
                if n.retry_count >= 3:
                    n.status, n.error = "failed", str(e)[:300]
                session.commit()
                if n.status != "failed":
                    raise  # 指数退避重试
                out[channel] = f"failed: {str(e)[:80]}"
        return out
    finally:
        session.close()
