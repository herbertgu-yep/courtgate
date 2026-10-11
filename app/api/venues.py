"""浏览类公开接口：场馆 / 场地 / 放场批次 / 可约单元视图。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_session
from app.models import Court, CourtSlot, Release, TimeSlot, Venue

router = APIRouter(prefix="/api", tags=["浏览"])


@router.get("/venues", summary="场馆列表")
async def list_venues(session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    rows = (await session.scalars(select(Venue).where(Venue.status == "active"))).all()
    return {
        "items": [
            {
                "id": v.id,
                "name": v.name,
                "address": v.address,
                "open_time": str(v.open_time),
                "close_time": str(v.close_time),
                "notice": v.notice,
            }
            for v in rows
        ]
    }


@router.get("/venues/{venue_id}", summary="场馆详情（含场地）")
async def venue_detail(venue_id: int, session: Annotated[AsyncSession, Depends(get_session)]) -> dict:
    v = await session.get(Venue, venue_id)
    if v is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("场馆不存在")
    courts = (await session.scalars(select(Court).where(Court.venue_id == venue_id, Court.status == "active"))).all()
    return {
        "id": v.id,
        "name": v.name,
        "address": v.address,
        "phone": v.phone,
        "open_time": str(v.open_time),
        "close_time": str(v.close_time),
        "notice": v.notice,
        "courts": [
            {"id": c.id, "name": c.name, "court_type": c.court_type, "base_price_cents": c.base_price_cents}
            for c in courts
        ],
    }


@router.get("/releases", summary="放场批次列表")
async def list_releases(
    session: Annotated[AsyncSession, Depends(get_session)],
    status: str | None = None,
    venue_id: int | None = None,
) -> dict:
    q = select(Release).order_by(Release.id.desc()).limit(50)
    if status:
        q = q.where(Release.status == status)
    if venue_id is not None:
        q = q.where(Release.venue_id == venue_id)
    rows = (await session.scalars(q)).all()
    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "venue_id": r.venue_id,
                "period_start": str(r.period_start),
                "period_end": str(r.period_end),
                "open_at": r.open_at,
                "close_at": r.close_at,
                "status": r.status,
                "per_user_limit": r.per_user_limit,
            }
            for r in rows
        ]
    }


@router.get("/releases/{release_id}/slots", summary="可约单元视图（选时段页数据源）")
async def release_slots(
    release_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    date: str | None = None,
) -> dict:
    """静态骨架（日期/场地/时段/价格）缓存于 Redis；可用性每请求从集合现算。"""
    import datetime as _dt
    import json as _json

    from redis.asyncio import Redis

    from app.cache import keys
    from app.cache.redis_client import get_async_redis

    release = await session.get(Release, release_id)
    if release is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("放场批次不存在")

    redis: Redis = get_async_redis()
    view_key = keys.slots_view(release_id)
    cached = await redis.get(view_key)
    if cached:
        static = _json.loads(cached)
    else:
        slots = (await session.scalars(select(CourtSlot).where(CourtSlot.release_id == release_id))).all()
        ts_rows = (await session.scalars(select(TimeSlot).order_by(TimeSlot.sort_order))).all()
        court_rows = (await session.scalars(select(Court).where(Court.status == "active"))).all()
        ts_map = {t.id: t for t in ts_rows}
        court_map = {c.id: c for c in court_rows}
        static = {
            "dates": sorted({str(c.slot_date) for c in slots}),
            "time_slots": [{"id": t.id, "label": t.label, "price_ratio_bp": t.price_ratio_bp} for t in ts_rows],
            "slot_skeleton": [
                {
                    "court_slot_id": c.id,
                    "court_id": c.court_id,
                    "date": str(c.slot_date),
                    "time_slot_id": c.time_slot_id,
                    "label": ts_map[c.time_slot_id].label,
                    "price_cents": c.price_cents,
                }
                for c in slots
            ],
            "courts": {
                str(cid): {"court_id": cid, "court_name": court_map[cid].name, "court_type": court_map[cid].court_type}
                for cid in sorted({c.court_id for c in slots})
                if cid in court_map
            },
        }
        await redis.set(view_key, _json.dumps(static, ensure_ascii=False), ex=60 * 60 * 24 * 30)

    avail_key = keys.avail_set(release_id)
    members = await redis.smembers(avail_key)
    avail = {int(m) for m in members} if members else {c["court_slot_id"] for c in static["slot_skeleton"]}

    skeleton = static["slot_skeleton"]
    if date:
        skeleton = [c for c in skeleton if c["date"] == date]

    # 闭馆日：本批次周期内该场馆的全部休息日；命中请求日期时全部时段不可约
    from app.models import VenueClosure

    closed_dates: list[str] = []
    if static["dates"]:
        closed_rows = (
            await session.scalars(
                select(VenueClosure.closure_date).where(
                    VenueClosure.venue_id == release.venue_id,
                    VenueClosure.closure_date.in_([_dt.date.fromisoformat(d) for d in static["dates"]]),
                )
            )
        ).all()
        closed_dates = sorted(str(d) for d in closed_rows)
    is_closed = bool(date and date[:10] in closed_dates)
    if is_closed:
        skeleton = [{**c, "available": False} for c in skeleton]

    return {
        "release_id": release_id,
        "release_status": release.status,
        "open_at": release.open_at,
        "per_user_limit": release.per_user_limit,
        "closed": is_closed,
        "closed_dates": closed_dates,
        "dates": static["dates"],
        "time_slots": static["time_slots"],
        "courts": [
            {
                **static["courts"][cid],
                "slots": [
                    {
                        "court_slot_id": c["court_slot_id"],
                        "date": c["date"],
                        "time_slot_id": c["time_slot_id"],
                        "label": c["label"],
                        "price_cents": c["price_cents"],
                        "available": (c["court_slot_id"] in avail) and not is_closed,
                    }
                    for c in skeleton
                    if c["court_id"] == int(cid)
                ],
            }
            for cid in sorted(static["courts"], key=int)
        ],
    }
