"""提供方注册表。"""

from __future__ import annotations

from app.services.oauth.base import OAuthProvider
from app.services.oauth.mock_wechat import MockWechatProvider

PROVIDERS: dict[str, OAuthProvider] = {MockWechatProvider.code: MockWechatProvider()}


def get_provider(code: str) -> OAuthProvider:
    if code not in PROVIDERS:
        from app.core.exceptions import NotFoundError

        raise NotFoundError(f"不支持的第三方登录渠道：{code}")
    return PROVIDERS[code]


def list_providers() -> list[dict]:
    return [{"code": p.code, "label": p.label} for p in PROVIDERS.values()]
