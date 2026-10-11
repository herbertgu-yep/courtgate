"""依赖注入：路由函数禁止自行创建会话/Redis，一律 Depends。测试用 dependency_overrides 替换。"""

from __future__ import annotations

from typing import Annotated

# Header 形式取 token（比 OAuth2PasswordBearer 更直接，/docs 里手填 Bearer）
from fastapi import Depends, Header, Request
from fastapi.security.utils import get_authorization_scheme_param
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_session
from app.models import User


async def get_redis() -> Redis:
    """异步 Redis 客户端（惰性导入避免循环依赖）。"""
    from app.cache.redis_client import get_async_redis

    return await get_async_redis()


async def get_current_user(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    token = _extract_token(request, authorization)
    try:
        user_id = decode_token(token, expected_type="access")
    except ValueError as e:
        raise UnauthorizedError("登录已过期，请重新登录") from e
    user = await session.get(User, user_id)
    if user is None or user.status != 1:
        raise UnauthorizedError("账号不存在或已被禁用")
    request.state.user_id = user.id
    return user


async def require_operator(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "operator":
        raise ForbiddenError("需要管理员权限")
    return user


def _extract_token(request: Request, authorization: str | None) -> str:
    auth = authorization or request.headers.get("authorization", "")
    scheme, token = get_authorization_scheme_param(auth)
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedError("未提供有效的登录凭证")
    return token
