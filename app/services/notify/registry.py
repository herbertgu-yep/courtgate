"""通知渠道注册表。"""

from __future__ import annotations

from app.services.notify.base import Notifier

_registered: dict[str, Notifier] = {}


def register(notifier: Notifier) -> None:
    _registered[notifier.channel] = notifier


def get_notifier(channel: str) -> Notifier | None:
    return _registered.get(channel)


def all_channels() -> list[str]:
    return list(_registered)
