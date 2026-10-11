"""邮件渠道：配置 SMTP 才启用；渲染后经 aiosmtplib 发送。"""

from __future__ import annotations

from typing import Any

from app.models import User
from app.services.notify.base import Notifier
from app.services.notify.inbox import render


class EmailNotifier(Notifier):
    channel = "email"

    def enabled(self) -> bool:
        from app.core.config import get_settings

        s = get_settings()
        return bool(s.smtp_host)

    async def send(self, user: User, template_code: str, context: dict[str, Any]) -> tuple[str, str]:
        if not self.enabled():
            raise RuntimeError("SMTP 未配置")
        from email.mime.text import MIMEText
        from email.utils import formataddr

        import aiosmtplib

        from app.core.config import get_settings

        s = get_settings()
        title, content = render(template_code, context)
        msg = MIMEText(content, "plain", "utf-8")
        msg["Subject"] = title
        msg["From"] = formataddr(("CourtGate", s.smtp_from))
        msg["To"] = user.username
        await aiosmtplib.send(
            msg,
            hostname=s.smtp_host,
            port=s.smtp_port,
            username=s.smtp_user or None,
            password=s.smtp_password or None,
            start_tls=True,
        )
        return title, content
