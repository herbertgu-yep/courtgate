"""站内信路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_session
from app.models import Notification, User

router = APIRouter(prefix="/api/notifications", tags=["通知"])


@router.get("", summary="站内信列表")
async def list_notifications(
    session: Annotated[AsyncSession, Depends(get_session)], user: Annotated[User, Depends(get_current_user)]
) -> dict:
    rows = (
        await session.scalars(
            select(Notification)
            .where(Notification.user_id == user.id, Notification.channel == "inbox")
            .order_by(Notification.id.desc())
            .limit(50)
        )
    ).all()
    return {
        "items": [
            {
                "id": n.id,
                "template_code": n.template_code,
                "title": n.title,
                "content": n.content,
                "is_read": bool(n.is_read),
                "created_at": n.created_at,
            }
            for n in rows
        ]
    }


@router.post("/{notification_id}/read", summary="标记已读")
async def mark_read(
    notification_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    n = await session.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("通知不存在")
    n.is_read = 1
    await session.commit()
    return {"id": n.id, "is_read": True}


@router.post("/read-all", summary="全部已读")
async def read_all(
    session: Annotated[AsyncSession, Depends(get_session)], user: Annotated[User, Depends(get_current_user)]
) -> dict:
    await session.execute(
        update(Notification).where(Notification.user_id == user.id, Notification.is_read == 0).values(is_read=1)
    )
    await session.commit()
    return {"ok": True}
