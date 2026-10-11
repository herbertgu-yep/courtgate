"""第三方登录抽象：业务代码只认 OAuthProvider，不出现 if provider == 分支。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class OAuthUser(BaseModel):
    openid: str
    unionid: str = ""
    nickname: str = ""


class OAuthProvider(ABC):
    code: str
    label: str

    @abstractmethod
    async def exchange_code(self, code: str) -> OAuthUser:
        """用前端 code 换第三方用户标识；失败抛 OAuthCodeInvalidError。"""
