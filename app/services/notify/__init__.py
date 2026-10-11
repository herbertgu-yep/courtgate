"""通知渠道装配：import 即注册。"""

from app.services.notify.email import EmailNotifier
from app.services.notify.inbox import InboxNotifier
from app.services.notify.sms import SmsNotifier

__all__ = ["InboxNotifier", "EmailNotifier", "SmsNotifier"]
