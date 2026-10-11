"""通知渠道抽象：新增渠道 = 实现类 + 注册，业务代码零分支。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models import User


class Notifier(ABC):
    channel: str

    @abstractmethod
    async def send(self, user: User, template_code: str, context: dict[str, Any]) -> tuple[str, str]:
        """返回 (title, content)；抛异常视为发送失败。"""
