"""会员与积分路由。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_session
from app.models import PointsLedger, User
from app.services import member_service

router = APIRouter(prefix="/api", tags=["会员与积分"])


@router.get("/members/levels", summary="等级定义与权益")
async def levels(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    rows = await member_service.all_levels(session)
    return {
        "items": [
            {
                "code": lv.code,
                "name": lv.name,
                "min_spent_cents": lv.min_spent_cents,
                "discount_bp": lv.discount_bp,
                "points_rate_bp": lv.points_rate_bp,
            }
            for lv in rows
        ]
    }


@router.get("/members/me", summary="我的等级与升级进度")
async def my_member(
    session: Annotated[AsyncSession, Depends(get_session)], user: Annotated[User, Depends(get_current_user)]
) -> dict:
    current = await member_service.level_for(session, user.member_level)
    levels = await member_service.all_levels(session)
    nxt = min(
        (lv for lv in levels if lv.min_spent_cents > user.total_spent_cents),
        key=lambda lv: lv.min_spent_cents,
        default=None,
    )
    return {
        "member_level": user.member_level,
        "level_name": current.name if current else user.member_level,
        "discount_bp": current.discount_bp if current else 10000,
        "total_spent_cents": user.total_spent_cents,
        "next_level": {"code": nxt.code, "name": nxt.name, "need_cents": nxt.min_spent_cents - user.total_spent_cents}
        if nxt
        else None,
    }


@router.get("/points/balance", summary="积分余额")
async def points_balance(user: Annotated[User, Depends(get_current_user)]) -> dict:
    return {"balance": user.points_balance}


@router.get("/points/ledger", summary="积分流水")
async def points_ledger(
    session: Annotated[AsyncSession, Depends(get_session)],
    user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    size: int = Query(20, le=100),
) -> dict:
    q = select(PointsLedger).where(PointsLedger.user_id == user.id).order_by(PointsLedger.id.desc())
    total = await session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = (await session.scalars(q.offset((page - 1) * size).limit(size))).all()
    return {
        "items": [
            {
                "change_type": r.change_type,
                "points": r.points,
                "balance_after": r.balance_after,
                "ref_booking_no": r.ref_booking_no,
                "remark": r.remark,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
    }
