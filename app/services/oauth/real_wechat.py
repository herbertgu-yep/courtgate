"""真实微信 H5 网页授权骨架：需要公众号 appid 与 secret。

真实流程（H5 网页授权，与小程序的 jscode2session 是两套）：
1. 前端跳转 https://open.weixin.qq.com/connect/oauth2/authorize?...&scope=snsapi_base
2. 微信回调带 code，后端 GET https://api.weixin.qq.com/sns/oauth2/access_token
   ?appid=&secret=&code=&grant_type=authorization_code 换 openid
3. 实现本类 exchange_code 并注册到 registry 即可，业务代码零改动。
"""

from __future__ import annotations

from app.services.oauth.base import OAuthProvider, OAuthUser


class RealWechatProvider(OAuthProvider):
    code = "wechat_real"
    label = "微信登录（真实，未接入）"

    async def exchange_code(self, code: str) -> OAuthUser:
        raise NotImplementedError("需要公众号 appid 与 secret，参见 docs/OAUTH_INTEGRATION.md")
