"""第三方登录与绑定：账号以手机号为准，微信不能凭空建号。"""

from __future__ import annotations

import json
import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import keys
from app.core.exceptions import ForbiddenError, NotFoundError, OAuthAccountNotBoundError
from app.core.logging import get_logger
from app.core.metrics import oauth_login_total
from app.core.security import create_access_token, create_refresh_token, verify_password
from app.models import OAuthAccount, User
from app.services.oauth.registry import get_provider

log = get_logger("courtgate.oauth")
TICKET_TTL = 300


async def login_with_code(session: AsyncSession, redis: Redis, *, provider_code: str, code: str) -> dict:
    """第三方登录：已绑定 → 签发令牌；未绑定 → 返回一次性 ticket 走绑定流程。"""
    provider = get_provider(provider_code)
    oauth_user = await provider.exchange_code(code)
    account = await session.scalar(
        select(OAuthAccount).where(OAuthAccount.provider == provider_code, OAuthAccount.openid == oauth_user.openid)
    )
    if account is not None:
        user = await session.get(User, account.user_id)
        if user is None or user.status != 1:
            raise NotFoundError("账号不存在或已禁用")
        oauth_login_total.labels(provider=provider_code, bound="true").inc()
        return {
            "bound": True,
            "access_token": create_access_token(user.id),
            "refresh_token": create_refresh_token(user.id),
            "nickname": user.nickname,
        }
    ticket = uuid.uuid4().hex
    await redis.set(
        keys.oauth_ticket(ticket),
        json.dumps(
            {
                "provider": provider_code,
                "openid": oauth_user.openid,
                "unionid": oauth_user.unionid,
                "nickname": oauth_user.nickname,
            },
            ensure_ascii=False,
        ),
        ex=TICKET_TTL,
    )
    oauth_login_total.labels(provider=provider_code, bound="false").inc()
    raise OAuthAccountNotBoundError(details={"ticket": ticket, "provider": provider_code})


async def bind(session: AsyncSession, redis: Redis, *, ticket: str, username: str, password: str) -> dict:
    """绑定：ticket 校验 → 学号/手机号密码校验 → 建绑定关系 → 签发令牌。"""
    raw = await redis.get(keys.oauth_ticket(ticket))
    if raw is None:
        raise ForbiddenError("绑定凭证无效或已过期，请重新发起登录")
    info = json.loads(raw)
    await redis.delete(keys.oauth_ticket(ticket))

    user = await session.scalar(select(User).where(User.username == username))
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        raise ForbiddenError("用户名或密码错误")
    if user.status != 1:
        raise ForbiddenError("账号已被禁用")
    dup = await session.scalar(
        select(OAuthAccount).where(OAuthAccount.provider == info["provider"], OAuthAccount.openid == info["openid"])
    )
    if dup is not None:
        raise ForbiddenError("该第三方账号已绑定其他用户")
    session.add(
        OAuthAccount(
            user_id=user.id,
            provider=info["provider"],
            openid=info["openid"],
            unionid=info.get("unionid", ""),
            nickname=info.get("nickname", ""),
        )
    )
    await session.commit()
    log.info("oauth_bound", user_id=user.id, provider=info["provider"])
    return {
        "bound": True,
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "nickname": user.nickname,
    }
