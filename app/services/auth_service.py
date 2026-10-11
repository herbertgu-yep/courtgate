"""认证：注册 / 登录 / 刷新。"""

from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedError
from app.core.logging import get_logger
from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models import User


async def register(
    session: AsyncSession,
    redis: Redis,
    *,
    username: str,
    password: str,
    nickname: str = "",
    captcha_id: str = "",
    captcha_code: str = "",
) -> User:
    from app.core.password import assert_password, assert_username

    assert_username(username)
    assert_password(password)
    await verify_captcha(redis, captcha_id=captcha_id, code=captcha_code)
    exists = await session.scalar(select(User).where(User.username == username))
    if exists:
        raise UnauthorizedError("该用户名已被注册")
    user = User(
        username=username,
        password_hash=hash_password(password),
        nickname=nickname or username[:2] + "****" + username[-2:],
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def login(
    session: AsyncSession, redis: Redis, *, username: str, password: str, captcha_id: str = "", captcha_code: str = ""
) -> dict:
    user = await session.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedError("用户名或密码错误")
    # 密码登录失败次数不设限（bcrypt 天然抗爆破），但验证码必须有效
    await verify_captcha(redis, captcha_id=captcha_id, code=captcha_code)
    if user.status != 1:
        raise UnauthorizedError("账号已被禁用")
    return _token_pair(user)


async def refresh(session: AsyncSession, *, refresh_token: str) -> dict:
    try:
        user_id = decode_token(refresh_token, expected_type="refresh")
    except ValueError as e:
        raise UnauthorizedError("刷新凭证无效") from e
    user = await session.get(User, user_id)
    if user is None:
        raise UnauthorizedError("账号不存在")
    return _token_pair(user)


def _token_pair(user: User) -> dict:
    return {
        "access_token": create_access_token(user.id),
        "refresh_token": create_refresh_token(user.id),
        "nickname": user.nickname,
        "role": user.role,
    }


log = get_logger("courtgate.auth")


# ---------------------------------------------------------------- 图形验证码


async def create_captcha(redis: Redis) -> dict:
    """生成图形验证码：图片 + 一次性 id（Redis 5 分钟）。"""
    import datetime as dt

    from app.cache import keys
    from app.core.captcha import generate

    captcha_id, text, image = generate()
    await redis.set(keys.captcha(captcha_id), text.upper(), ex=300)
    return {
        "captcha_id": captcha_id,
        "image": image,
        "ttl": 300,
        "created_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
    }


async def verify_captcha(redis: Redis, *, captcha_id: str, code: str) -> None:
    """校验图形验证码：一次性使用，不区分大小写。失败或过期抛 401。"""
    from app.cache import keys

    stored = await redis.get(keys.captcha(captcha_id))
    await redis.delete(keys.captcha(captcha_id))  # 一次性：无论对错都作废，防爆破
    if stored is None:
        raise UnauthorizedError("验证码已过期，请刷新后重试")
    if stored.strip().upper() != code.strip().upper():
        raise UnauthorizedError("验证码错误")
