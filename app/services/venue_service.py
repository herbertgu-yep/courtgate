"""场馆配置与闭馆：营业时间/休息/时段粒度校验、场馆 CRUD、闭馆冲突处理。

约束规则：
- 编辑场馆配置不触碰已有数据，只对之后放场的批次生效；
- 设置休息日先返回受影响预约预览，确认后待支付单自动取消、已支付单自动退款，
  时段归还、优惠券返还、赠送积分扣回、款项原路退回，并向用户投递闭馆通知。
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Iterable
from datetime import date

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ClosureConflictError, CourtGateError, NotFoundError
from app.core.logging import get_logger
from app.models import (
    Booking,
    BookingItem,
    Court,
    Release,
    User,
    Venue,
    VenueClosure,
)
from app.services import booking_service

log = get_logger("courtgate.venue")

PHONE_RE = re.compile(r"^(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8}|400-?\d{3}-?\d{3,4})$")
ALLOWED_SLOT_MINUTES = (30, 60, 90, 120)
ALLOWED_PEAK_RATIOS = (12500, 15000, 20000)
MAX_BREAKS = 4


def _invalid(msg: str) -> CourtGateError:
    e = CourtGateError(msg)
    e.code = "VALIDATION_ERROR"
    e.http_status = 422
    return e


def _hm(value: str) -> int:
    """'HH:MM' → 当天分钟数；非法输入抛业务异常。"""
    parts = value.split(":")
    if len(parts) != 2:
        raise _invalid(f"时间格式不合法：{value}")
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError as e:
        raise _invalid(f"时间格式不合法：{value}") from e
    if not (0 <= h < 24 and 0 <= m < 60):
        raise _invalid(f"时间格式不合法：{value}")
    return h * 60 + m


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_breaks(raw: object) -> list[dict]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            raise _invalid("休息时段配置不合法") from e
    if not isinstance(raw, list):
        raise _invalid("休息时段配置不合法")
    return raw


def validate_venue_config(
    *,
    open_time: str,
    close_time: str,
    breaks: object,
    slot_minutes: int,
    peak_start: str | None = None,
    peak_end: str | None = None,
    peak_ratio_bp: int = 15000,
) -> tuple[list[dict], tuple[str | None, str | None, int]]:
    """校验营业配置，返回（规范化休息窗口, (高峰开始, 高峰结束, 倍率)）。

    区间约束：休息、高峰都须落在营业时间内；休息之间、休息与高峰互不重叠。
    """
    open_m, close_m = _hm(open_time), _hm(close_time)
    if open_m >= close_m:
        raise _invalid("营业开始时间必须早于结束时间")
    if int(slot_minutes) not in ALLOWED_SLOT_MINUTES:
        raise _invalid(f"预约时段粒度仅支持 {'/'.join(map(str, ALLOWED_SLOT_MINUTES))} 分钟")
    peak = _validate_peak(open_m, close_m, peak_start, peak_end, int(peak_ratio_bp))
    raw = parse_breaks(breaks)
    if len(raw) > MAX_BREAKS:
        raise _invalid(f"休息窗口最多 {MAX_BREAKS} 个")
    windows: list[tuple[int, int]] = []
    for b in raw:
        try:
            bs, be = _hm(b["start"]), _hm(b["end"])
        except (KeyError, TypeError) as e:
            raise _invalid("休息时段配置不合法") from e
        if bs >= be:
            raise _invalid("休息窗口开始必须早于结束")
        if bs < open_m or be > close_m:
            raise _invalid("休息窗口必须落在营业时间内")
        windows.append((bs, be))
    windows.sort()
    for (_, e1), (s2, _) in zip(windows, windows[1:], strict=False):
        if s2 < e1:
            raise _invalid("休息窗口不能重叠")
    if peak[0] is not None and peak[1] is not None:
        ps, pe = _hm(peak[0]), _hm(peak[1])
        for bs, be in windows:
            if ps < be and bs < pe:
                raise _invalid("高峰时段与休息窗口不能重叠")
    return [{"start": _fmt(s), "end": _fmt(e)} for s, e in windows], peak


def _validate_peak(
    open_m: int, close_m: int, peak_start: str | None, peak_end: str | None, peak_ratio_bp: int
) -> tuple[str | None, str | None, int]:
    """高峰窗口校验：两头都空 = 无高峰；给则须落在营业时间内且开始早于结束。"""
    if bool(peak_start) != bool(peak_end):
        raise _invalid("高峰时段需要同时填写开始与结束时间")
    if not peak_start or not peak_end:
        return None, None, 10000
    ps, pe = _hm(peak_start), _hm(peak_end)
    if ps >= pe:
        raise _invalid("高峰时段开始必须早于结束")
    if ps < open_m or pe > close_m:
        raise _invalid("高峰时段必须落在营业时间内")
    if peak_ratio_bp not in ALLOWED_PEAK_RATIOS:
        raise _invalid(f"高峰倍率仅支持 {'、'.join('×' + str(r / 10000) for r in ALLOWED_PEAK_RATIOS)}")
    return _fmt(ps), _fmt(pe), peak_ratio_bp


def build_slot_defs(venue: Venue) -> list[dict]:
    """按场馆配置切出时段定义：粒度 = slot_minutes，休息窗口整段跳过。

    高峰按场馆配置计价（时段开始时刻落在高峰窗口内），未配置则全时段基础价。
    """
    open_m, close_m = _hm(str(venue.open_time)[:5]), _hm(str(venue.close_time)[:5])
    windows = [(_hm(b["start"]), _hm(b["end"])) for b in parse_breaks(venue.breaks_json)]
    peak_s = _hm(str(venue.peak_start_time)[:5]) if venue.peak_start_time else None
    peak_e = _hm(str(venue.peak_end_time)[:5]) if venue.peak_end_time else None
    peak_bp = venue.peak_ratio_bp
    step = venue.slot_minutes
    defs: list[dict] = []
    cur = open_m
    while cur + step <= close_m:
        nxt = cur + step
        hit = next((w for w in windows if cur < w[1] and nxt > w[0]), None)
        if hit is not None:
            cur = hit[1]  # 跳到休息结束，重新切
            continue
        ratio = peak_bp if peak_s is not None and peak_e is not None and peak_s <= cur < peak_e else 10000
        defs.append(
            {"start": _fmt(cur), "end": _fmt(nxt), "label": f"{_fmt(cur)}-{_fmt(nxt)}", "price_ratio_bp": ratio}
        )
        cur = nxt
    return defs


# ---------------------------------------------------------------- 场馆 CRUD


def serialize_venue(v: Venue, court_count: int = 0, closure_count: int = 0, release_count: int = 0) -> dict:
    return {
        "id": v.id,
        "name": v.name,
        "address": v.address,
        "phone": v.phone,
        "open_time": str(v.open_time)[:5],
        "close_time": str(v.close_time)[:5],
        "breaks": parse_breaks(v.breaks_json),
        "slot_minutes": v.slot_minutes,
        "peak_start_time": str(v.peak_start_time)[:5] if v.peak_start_time else None,
        "peak_end_time": str(v.peak_end_time)[:5] if v.peak_end_time else None,
        "peak_ratio_bp": v.peak_ratio_bp if v.peak_start_time else None,
        "notice": v.notice,
        "status": v.status,
        "court_count": court_count,
        "closure_count": closure_count,
        "release_count": release_count,
    }


async def list_venues(session: AsyncSession) -> dict:
    rows = (await session.scalars(select(Venue).order_by(Venue.id))).all()
    items = []
    for v in rows:
        court_count = await session.scalar(select(func.count()).select_from(Court).where(Court.venue_id == v.id)) or 0
        closure_count = (
            await session.scalar(select(func.count()).select_from(VenueClosure).where(VenueClosure.venue_id == v.id))
            or 0
        )
        release_count = (
            await session.scalar(select(func.count()).select_from(Release).where(Release.venue_id == v.id)) or 0
        )
        items.append(serialize_venue(v, court_count, closure_count, release_count))
    return {"items": items}


async def create_venue(session: AsyncSession, body: dict) -> dict:
    breaks, (peak_s, peak_e, peak_bp) = validate_venue_config(
        open_time=body["open_time"],
        close_time=body["close_time"],
        breaks=body.get("breaks", []),
        slot_minutes=body.get("slot_minutes", 60),
        peak_start=body.get("peak_start_time") or None,
        peak_end=body.get("peak_end_time") or None,
        peak_ratio_bp=int(body.get("peak_ratio_bp") or 15000),
    )
    court_count = int(body.get("court_count", 1))
    base_price_cents = int(body.get("base_price_cents", 0))
    if not 1 <= court_count <= 99:
        raise _invalid("场地数量需在 1~99 之间")
    if base_price_cents < 100:
        raise _invalid("场地单价至少 1 元")
    phone = str(body.get("phone", "") or "").strip()
    if phone and not PHONE_RE.fullmatch(phone):
        raise _invalid("联系电话格式不正确（支持手机号或座机，如 13800138000 / 0571-88880000）")
    v = Venue(
        name=body["name"],
        address=body.get("address", ""),
        phone=phone,
        open_time=body["open_time"],
        close_time=body["close_time"],
        breaks_json=json.dumps(breaks, ensure_ascii=False),
        slot_minutes=int(body.get("slot_minutes", 60)),
        peak_start_time=peak_s,
        peak_end_time=peak_e,
        peak_ratio_bp=peak_bp,
        notice=body.get("notice", ""),
    )
    session.add(v)
    await session.flush()
    for i in range(court_count):
        session.add(Court(venue_id=v.id, name=f"{i + 1} 号场", base_price_cents=base_price_cents))
    await session.commit()
    await session.refresh(v)
    log.info("venue_created", venue_id=v.id, name=v.name, courts=court_count)
    return serialize_venue(v, court_count)


async def update_venue(session: AsyncSession, venue_id: int, body: dict) -> dict:
    v = await session.get(Venue, venue_id)
    if v is None:
        raise NotFoundError("场馆不存在")
    open_time = body.get("open_time", str(v.open_time)[:5])
    close_time = body.get("close_time", str(v.close_time)[:5])
    breaks = body.get("breaks", parse_breaks(v.breaks_json))
    slot_minutes = body.get("slot_minutes", v.slot_minutes)
    breaks, (peak_s, peak_e, peak_bp) = validate_venue_config(
        open_time=open_time,
        close_time=close_time,
        breaks=breaks,
        slot_minutes=slot_minutes,
        peak_start=body.get("peak_start_time") or None,
        peak_end=body.get("peak_end_time") or None,
        peak_ratio_bp=int(body.get("peak_ratio_bp") or v.peak_ratio_bp or 15000),
    )
    v.name = body.get("name", v.name)
    v.address = body.get("address", v.address)
    if "phone" in body:
        phone = str(body.get("phone") or "").strip()
        if phone and not PHONE_RE.fullmatch(phone):
            raise _invalid("联系电话格式不正确（支持手机号或座机，如 13800138000 / 0571-88880000）")
        v.phone = phone
    v.notice = body.get("notice", v.notice)
    v.open_time, v.close_time = open_time, close_time
    v.breaks_json = json.dumps(breaks, ensure_ascii=False)
    v.slot_minutes = int(slot_minutes)
    v.peak_start_time, v.peak_end_time, v.peak_ratio_bp = peak_s, peak_e, peak_bp
    await session.commit()
    await session.refresh(v)
    out = serialize_venue(v)
    out["slot_defs"] = build_slot_defs(v)
    return out


async def venue_detail(session: AsyncSession, venue_id: int) -> dict:
    v = await session.get(Venue, venue_id)
    if v is None:
        raise NotFoundError("场馆不存在")
    courts = (await session.scalars(select(Court).where(Court.venue_id == venue_id).order_by(Court.id))).all()
    closures = (
        await session.scalars(
            select(VenueClosure).where(VenueClosure.venue_id == venue_id).order_by(VenueClosure.closure_date.desc())
        )
    ).all()
    out = serialize_venue(v, len(courts), len(closures))
    out["courts"] = [{"id": c.id, "name": c.name, "base_price_cents": c.base_price_cents} for c in courts]
    out["closures"] = [
        {
            "id": c.id,
            "closure_date": str(c.closure_date),
            "affected_bookings": c.affected_bookings,
            "notify_content": c.notify_content,
        }
        for c in closures
    ]
    out["slot_defs"] = build_slot_defs(v)
    return out


# ---------------------------------------------------------------- 闭馆


async def assert_dates_open(session: AsyncSession, venue_id: int, dates: Iterable[date]) -> None:
    """预约/试算前校验：日期不在场馆休息日内。"""
    from app.core.exceptions import VenueClosedError

    closed = (
        await session.scalars(
            select(VenueClosure.closure_date).where(
                VenueClosure.venue_id == venue_id, VenueClosure.closure_date.in_(sorted(dates))
            )
        )
    ).all()
    if closed:
        raise VenueClosedError(details={"dates": sorted(str(d) for d in closed)})


async def _affected_bookings(session: AsyncSession, venue_id: int, closure_date: object) -> list[Booking]:
    """按 场地集合 + 预约项日期 查受影响预约（不依赖时段引用，取消单亦可统计）。"""
    court_ids = (await session.scalars(select(Court.id).where(Court.venue_id == venue_id))).all()
    rows = (
        await session.scalars(
            select(Booking)
            .distinct()
            .join(BookingItem, BookingItem.booking_no == Booking.booking_no)
            .where(
                BookingItem.court_id.in_(court_ids),
                BookingItem.slot_date == closure_date,
                Booking.status.in_(["pending_paid", "paid"]),
            )
        )
    ).all()
    return list(rows)


def _preview_rows(
    session: AsyncSession, bookings: list[Booking], items_map: dict[str, list[BookingItem]], users: dict[int, User]
) -> list[dict]:
    return [
        {
            "booking_no": b.booking_no,
            "user_nickname": users[b.user_id].nickname if b.user_id in users else "",
            "user_phone": users[b.user_id].phone_number if b.user_id in users else None,
            "status": b.status,
            "total_cents": b.total_cents,
            "time_labels": "、".join(i.time_label for i in items_map.get(b.booking_no, [])),
        }
        for b in bookings
    ]


async def closure_preview(session: AsyncSession, venue_id: int, closure_date: dt.date) -> dict:
    v = await session.get(Venue, venue_id)
    if v is None:
        raise NotFoundError("场馆不存在")
    bookings = await _affected_bookings(session, venue_id, closure_date)
    nos = [b.booking_no for b in bookings]
    items_map: dict[str, list[BookingItem]] = {}
    if nos:
        for it in (
            await session.scalars(select(BookingItem).where(BookingItem.booking_no.in_(nos)).order_by(BookingItem.id))
        ).all():
            items_map.setdefault(it.booking_no, []).append(it)
    users = (
        {u.id: u for u in (await session.scalars(select(User).where(User.id.in_([b.user_id for b in bookings])))).all()}
        if bookings
        else {}
    )
    return {
        "closure_date": str(closure_date),
        "venue_name": v.name,
        "count": len(bookings),
        "bookings": _preview_rows(session, bookings, items_map, users),
    }


async def list_closures(session: AsyncSession, venue_id: int) -> dict:
    rows = (
        await session.scalars(
            select(VenueClosure).where(VenueClosure.venue_id == venue_id).order_by(VenueClosure.closure_date.desc())
        )
    ).all()
    return {
        "items": [
            {
                "id": c.id,
                "closure_date": str(c.closure_date),
                "affected_bookings": c.affected_bookings,
                "notify_content": c.notify_content,
                "created_at": c.created_at,
            }
            for c in rows
        ]
    }


async def apply_closure(
    session: AsyncSession,
    redis: Redis,
    *,
    venue_id: int,
    closure_date: dt.date | str,
    notify_content: str | None,
    force: bool,
    created_by: int,
) -> dict:
    """设置休息日。有受影响预约且未确认时抛 409 预览；确认后统一取消/退款并通知。"""
    v = await session.get(Venue, venue_id)
    if v is None:
        raise NotFoundError("场馆不存在")
    closure_date = dt.date.fromisoformat(str(closure_date)[:10]) if isinstance(closure_date, str) else closure_date
    dup = await session.scalar(
        select(VenueClosure).where(VenueClosure.venue_id == venue_id, VenueClosure.closure_date == closure_date)
    )
    if dup is not None:
        e = CourtGateError(f"{closure_date} 已设置过休息")
        e.code = "CLOSURE_EXISTS"
        e.http_status = 409
        raise e
    bookings = await _affected_bookings(session, venue_id, closure_date)
    if bookings and not force:
        preview = await closure_preview(session, venue_id, closure_date)
        raise ClosureConflictError(details={"preview": preview})
    session.add(
        VenueClosure(
            venue_id=venue_id,
            closure_date=closure_date,
            notify_content=notify_content,
            affected_bookings=len(bookings),
            created_by=created_by,
        )
    )
    actions: list[tuple[Booking, str]] = []
    for b in bookings:
        action = await booking_service.close_booking_for_closure(session, redis, b)
        actions.append((b, action))
        # 站内信与主事务同批落库：一笔预约一条，ref_id=预约单号保证幂等
        await booking_service.dispatch_closure_notice(
            session, b, venue_name=v.name, date=str(closure_date), action=action, custom=notify_content
        )
    await session.commit()
    log.info(
        "venue_closure_applied",
        venue_id=venue_id,
        date=str(closure_date),
        cancelled=sum(1 for _, a in actions if a == "cancelled"),
        refunded=sum(1 for _, a in actions if a == "refunded"),
    )
    return {
        "closure_date": str(closure_date),
        "affected": len(actions),
        "cancelled": sum(1 for _, a in actions if a == "cancelled"),
        "refunded": sum(1 for _, a in actions if a == "refunded"),
    }
