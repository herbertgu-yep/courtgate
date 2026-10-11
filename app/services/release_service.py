"""放场：按「场地 × 日期 × 时段」批量生成可约单元，幂等，灌 Redis。"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ReleaseNotOpenError
from app.core.logging import get_logger
from app.core.metrics import releases_created_total
from app.core.money import bp_multiply
from app.models import BookingItem, Court, CourtSlot, Release, TimeSlot, Venue
from app.services import slot_service

log = get_logger("courtgate.release")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="seconds")


def _as_datetime(v: datetime | str) -> datetime:
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


def _as_date(v: date | str) -> date:
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    return v


async def create_release(
    session: AsyncSession,
    redis: Redis,
    *,
    venue_id: int,
    name: str,
    period_start: date,
    period_end: date,
    open_at: datetime,
    close_at: datetime,
    per_user_limit: int,
    created_by: int,
) -> dict:
    """创建放场批次并批量生成单元。幂等：同一(场地,日期,时段)不重复。"""
    period_start, period_end = _as_date(period_start), _as_date(period_end)
    open_at, close_at = _as_datetime(open_at), _as_datetime(close_at)
    if open_at.tzinfo is None:
        open_at = open_at.replace(tzinfo=UTC)
    if close_at.tzinfo is None:
        close_at = close_at.replace(tzinfo=UTC)
    venue = await session.get(Venue, venue_id)
    if venue is None or venue.status != "active":
        raise NotFoundError("场馆不存在或已停用")
    if period_start > period_end:
        raise NotFoundError("周期不合法")
    if open_at >= close_at:
        raise NotFoundError("开抢时间必须早于停约时间")

    # API 级幂等：同场馆同周期重复放场 → 返回已有批次（不产生空批次、不重复单元）
    existing = await session.scalar(
        select(Release).where(
            Release.venue_id == venue_id,
            Release.period_start == period_start,
            Release.period_end == period_end,
        )
    )
    if existing is not None:
        from sqlalchemy import func

        n = (
            await session.scalar(
                select(func.count())
                .select_from(CourtSlot)
                .where(CourtSlot.release_id == existing.id, CourtSlot.status == "free")
            )
            or 0
        )
        log.info("release_reused", release_id=existing.id, venue_id=venue_id)
        return {"release_id": existing.id, "generated": 0, "available": n, "per_user_limit": existing.per_user_limit}

    release = Release(
        name=name,
        venue_id=venue_id,
        period_start=period_start,
        period_end=period_end,
        open_at=_iso(open_at),
        close_at=_iso(close_at),
        per_user_limit=max(1, int(per_user_limit)),
        status="pending",
        created_by=created_by,
    )
    now = _utcnow()
    if now >= close_at:
        release.status = "closed"
    elif now >= open_at:
        release.status = "open"
    session.add(release)
    await session.flush()  # 拿 release_id

    created = await generate_release_slots(session, redis, release, venue, period_start, period_end)
    await session.commit()
    n_avail = await slot_service.init_available(redis, session, release.id)
    releases_created_total.labels(venue_id=str(venue_id)).inc()
    log.info("release_created", release_id=release.id, venue_id=venue_id, generated=created, available=n_avail)
    return {
        "release_id": release.id,
        "generated": created,
        "available": n_avail,
        "per_user_limit": release.per_user_limit,
    }


async def generate_release_slots(
    session: AsyncSession, redis: Redis, release: Release, venue: Venue, period_start: date, period_end: date
) -> int:
    """按场馆当前配置重切批次时段并生成可约单元（时段价格在此固化）。

    先清掉本批次旧切片与旧单元再重放，供放场与重生成共用。不提交事务。
    """
    courts = (await session.scalars(select(Court).where(Court.venue_id == venue.id, Court.status == "active"))).all()
    if not courts:
        from app.core.exceptions import CourtGateError

        raise CourtGateError("该场馆没有可用场地，请先在场馆管理中配置场地")
    from app.services.venue_service import build_slot_defs

    slot_defs = build_slot_defs(venue)
    if not slot_defs:
        from app.core.exceptions import CourtGateError

        raise CourtGateError("营业时间内切不出任何时段，请检查营业时间与休息窗口配置")
    old_ts = (await session.scalars(select(TimeSlot).where(TimeSlot.release_id == release.id))).all()
    for t in old_ts:
        await session.delete(t)
    await session.flush()
    ts_rows = [
        TimeSlot(
            release_id=release.id,
            start_time=d["start"],
            end_time=d["end"],
            label=d["label"],
            price_ratio_bp=d["price_ratio_bp"],
            sort_order=i,
        )
        for i, d in enumerate(slot_defs)
    ]
    session.add_all(ts_rows)
    await session.flush()

    days = (period_end - period_start).days + 1
    rows: list[dict] = []
    for d in range(days):
        slot_date = period_start + timedelta(days=d)
        for court in courts:
            for ts in ts_rows:
                rows.append(
                    {
                        "release_id": release.id,
                        "court_id": court.id,
                        "slot_date": slot_date,
                        "time_slot_id": ts.id,
                        "price_cents": bp_multiply(court.base_price_cents, ts.price_ratio_bp),
                        "status": "free",
                        "booking_no": "",
                    }
                )
    # 幂等：INSERT IGNORE + uk_slots_court_date_time，冲突行静默跳过
    from sqlalchemy.dialects.mysql import insert as mysql_insert

    created = 0
    for i in range(0, len(rows), 500):  # 分批插入，避免单条 SQL 过大
        stmt = mysql_insert(CourtSlot).values(rows[i : i + 500]).prefix_with("IGNORE")
        result = await session.execute(stmt)
        created += int(getattr(result, "rowcount", 0) or 0)
    return created


async def regenerate_release(session: AsyncSession, redis: Redis, release_id: int) -> dict:
    """按场馆当前配置重生成批次时段：仅当该批次从未产生过预约记录时允许。

    时段价格在放场时固化，场馆配置变更不会追溯旧批次；此入口用于
    "还没人预约就调整了配置" 的场景，让旧批次按新配置重新切分计价。
    """
    from fastapi import status as _status  # noqa: F401

    release = await session.get(Release, release_id)
    if release is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("放场批次不存在")
    # 任何预约记录（含已取消/已退款）都引用本批次的时段 → 不可重生成
    referenced = await session.scalar(
        select(func.count())
        .select_from(BookingItem)
        .join(CourtSlot, CourtSlot.id == BookingItem.court_slot_id)
        .where(CourtSlot.release_id == release_id)
    )
    if referenced:
        from app.core.exceptions import CourtGateError

        e = CourtGateError(f"该批次已有 {referenced} 条预约记录，无法重生成；请调整配置后新放一批")
        e.code = "RELEASE_REGENERATE_CONFLICT"
        e.http_status = 409
        raise e
    venue = await session.get(Venue, release.venue_id)
    assert venue is not None
    # 清空旧单元后按当前配置重切
    await session.execute(delete(CourtSlot).where(CourtSlot.release_id == release_id))
    await session.flush()
    created = await generate_release_slots(session, redis, release, venue, release.period_start, release.period_end)
    await session.commit()
    n_avail = await slot_service.init_available(redis, session, release_id)
    log.info("release_regenerated", release_id=release_id, generated=created, available=n_avail)
    return {"release_id": release_id, "generated": created, "available": n_avail}


async def ensure_open(session: AsyncSession, release_id: int) -> Release:
    """校验批次处于开放窗口，返回 release。"""
    release = await session.get(Release, release_id)
    if release is None:
        raise NotFoundError("放场批次不存在")
    now = _iso(_utcnow())
    # 开抢窗口读取时推导，不依赖 Beat 翻状态（Beat 只做列表展示的状态维护）
    if release.status in ("draft", "closed") or not (release.open_at <= now < release.close_at):
        raise ReleaseNotOpenError(
            details={"open_at": release.open_at, "close_at": release.close_at, "status": release.status}
        )
    return release
