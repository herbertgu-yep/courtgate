"""支付路由：渠道列表 / 创建支付单 / 回调。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_session
from app.models import User
from app.services import payment_service
from app.services.payment.registry import list_channels

router = APIRouter(prefix="/api/payments", tags=["支付"])


@router.get("/channels", summary="可用支付渠道")
async def channels() -> dict:
    return {"items": list_channels()}


@router.post("/mock_callback_body", summary="构造沙箱回调体（等同第三方服务器发起）")
async def mock_callback_body(body: dict, user: Annotated[User, Depends(get_current_user)]) -> dict:
    """沙箱收银台用：为沙箱渠道构造合法签名回调体（等同第三方服务器发起的通知）。
    真实渠道由第三方服务器直接回调，不走此端点。"""
    from app.core.config import get_settings
    from app.core.exceptions import NotFoundError
    from app.services.payment.registry import get_channel
    from app.services.payment_service import build_mock_callback

    channel = get_channel(body.get("channel", ""))
    if not channel.sandbox:
        raise NotFoundError("仅沙箱渠道可构造回调")
    return build_mock_callback(body["payment_no"], body.get("amount_cents", 0), secret=get_settings().payment_secret)


@router.post("/{booking_no}", summary="创建支付单", status_code=201)
async def create_payment(
    booking_no: str,
    body: dict,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    return await payment_service.create_payment(
        session, booking_no=booking_no, channel=body.get("channel", "mock_alipay"), user_id=user.id
    )


@router.post("/callback/{channel}", summary="支付回调（验签 + 幂等）")
async def callback(channel: str, body: dict, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    # 已处理过的回调一律返回 200，避免第三方无限重试
    return await payment_service.handle_callback(session, channel=channel, payload=body)
