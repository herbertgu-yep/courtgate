"""短信渠道：Mock 实现（只写日志），接口形状与真实一致，接入留 TODO。"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.models import User
from app.services.notify.base import Notifier
from app.services.notify.inbox import render

log = get_logger("courtgate.notify.sms")


class SmsNotifier(Notifier):
    channel = "sms"

    async def send(self, user: User, template_code: str, context: dict[str, Any]) -> tuple[str, str]:
        # TODO: 接入真实短信通道（阿里云/腾讯云短信），此处为 Mock
        title, content = render(template_code, context)
        log.info("sms_mock_sent", username=user.username, template=template_code)
        return title, content
