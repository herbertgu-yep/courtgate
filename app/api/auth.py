"""认证路由：注册 / 登录 / 刷新。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_redis, get_session
from app.models import User
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/register", summary="注册（需图形验证码）", status_code=201)
async def register(
    body: RegisterIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    user = await auth_service.register(
        session,
        redis,
        username=body.username,
        password=body.password,
        nickname=body.nickname,
        captcha_id=body.captcha_id,
        captcha_code=body.captcha_code,
    )
    return auth_service._token_pair(user)


@router.get("/captcha", summary="获取图形验证码（防刷，一次性）")
async def captcha(redis: Annotated[Redis, Depends(get_redis)]) -> dict:
    return await auth_service.create_captcha(redis)


@router.post("/login", summary="登录（需图形验证码）")
async def login(
    body: LoginIn, session: Annotated[AsyncSession, Depends(get_session)], redis: Annotated[Redis, Depends(get_redis)]
) -> dict:
    return await auth_service.login(
        session,
        redis,
        username=body.username,
        password=body.password,
        captcha_id=body.captcha_id,
        captcha_code=body.captcha_code,
    )


@router.post("/refresh", summary="刷新令牌")
async def refresh(body: RefreshIn, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    return await auth_service.refresh(session, refresh_token=body.refresh_token)


@router.get("/oauth/providers", summary="可用第三方登录渠道")
async def oauth_providers() -> dict:
    from app.services.oauth.registry import list_providers

    return {"items": list_providers()}


@router.post("/oauth/{provider}", summary="第三方登录（code 换令牌）")
async def oauth_login(
    provider: str,
    body: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    from app.core.exceptions import CourtGateError
    from app.services import oauth_service

    code = body.get("code", "")
    try:
        return await oauth_service.login_with_code(session, redis, provider_code=provider, code=code)
    except CourtGateError as e:
        # 未绑定：把 details 里的 ticket 透传给前端
        e.http_status = 409
        raise


@router.post("/oauth/{provider}/bind", summary="绑定已有账号（ticket + 手机号密码）")
async def oauth_bind(
    provider: str,
    body: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict:
    from app.services import oauth_service

    return await oauth_service.bind(
        session,
        redis,
        ticket=body.get("ticket", ""),
        username=body.get("username", ""),
        password=body.get("password", ""),
    )


@router.get("/me", summary="当前用户")
async def me(user: Annotated[User, Depends(get_current_user)]) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "phone_number": user.phone_number,
        "role": user.role,
        "member_level": user.member_level,
        "points_balance": user.points_balance,
    }


@router.patch("/me", summary="编辑个人资料（昵称 / 手机号）")
async def update_me(
    body: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    import re

    from sqlalchemy import update as _update

    nickname = str(body.get("nickname", "") or "").strip()
    phone = str(body.get("phone_number", "") or "").strip()
    if not 1 <= len(nickname) <= 20:
        from app.core.exceptions import CourtGateError

        e = CourtGateError("昵称需为 1~20 个字符")
        e.code = "VALIDATION_ERROR"
        e.http_status = 422
        raise e
    if phone and not re.fullmatch(r"1[3-9]\d{9}", phone):
        from app.core.exceptions import CourtGateError

        e = CourtGateError("手机号格式不正确")
        e.code = "VALIDATION_ERROR"
        e.http_status = 422
        raise e
    await session.execute(_update(User).where(User.id == user.id).values(nickname=nickname, phone_number=phone or None))
    await session.commit()
    return {"nickname": nickname, "phone_number": phone or None}


@router.post("/phone", summary="补充联系手机号（登录后引导，选填）")
async def update_phone(
    body: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    import re

    from sqlalchemy import update as _update

    phone = str(body.get("phone", "")).strip()
    if not re.fullmatch(r"1[3-9]\d{9}", phone):
        from app.core.exceptions import CourtGateError

        e = CourtGateError("手机号格式不正确")
        e.code = "VALIDATION_ERROR"
        e.http_status = 422
        raise e
    await session.execute(_update(User).where(User.id == user.id).values(phone_number=phone))
    await session.commit()
    return {"phone_number": phone}
