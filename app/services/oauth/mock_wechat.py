"""Mock 微信提供方：code 形如 mock:<openid>:<昵称>，本地零依赖演示。"""

from __future__ import annotations

from app.core.exceptions import OAuthCodeInvalidError
from app.services.oauth.base import OAuthProvider, OAuthUser


class MockWechatProvider(OAuthProvider):
    code = "wechat"
    label = "微信登录（模拟）"

    async def exchange_code(self, code: str) -> OAuthUser:
        if not code.startswith("mock:"):
            raise OAuthCodeInvalidError("code 格式不合法")
        parts = code.split(":", 2)
        if len(parts) != 3 or not parts[1]:
            raise OAuthCodeInvalidError("code 格式不合法")
        return OAuthUser(openid=parts[1], nickname=parts[2])
