"""会员：等级配置、按累计消费升级。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MemberLevel, User


async def all_levels(session: AsyncSession) -> list[MemberLevel]:
    return list((await session.scalars(select(MemberLevel).order_by(MemberLevel.sort_order))).all())


async def level_for(session: AsyncSession, code: str) -> MemberLevel | None:
    return await session.scalar(select(MemberLevel).where(MemberLevel.code == code))


async def effective_level(session: AsyncSession, user: User) -> MemberLevel | None:
    """按累计消费取应属等级（等级定义缺失时返回 None，按不打折处理）。"""
    levels = await all_levels(session)
    fit = [lv for lv in levels if user.total_spent_cents >= lv.min_spent_cents]
    return max(fit, key=lambda lv: lv.min_spent_cents) if fit else None


async def sync_user_level(session: AsyncSession, user: User) -> bool:
    """把 user.member_level 同步为应属等级；发生升级返回 True。"""
    target = await effective_level(session, user)
    if target is None or target.code == user.member_level:
        return False
    user.member_level = target.code
    return True
