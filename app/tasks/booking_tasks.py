"""超时取消预约：Celery 同步任务，幂等（CAS），重复执行无副作用。"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult

from app.cache import keys
from app.cache.lua_loader_sync import run_lua_sync
from app.cache.redis_client import get_sync_redis
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models import Booking, BookingItem, CourtSlot, StockFlow
from app.tasks.celery_app import celery_app

log = get_logger("courtgate.task.booking")


@celery_app.task(
    name="app.tasks.booking_tasks.cancel_expired_booking", autoretry_for=(Exception,), retry_backoff=True, max_retries=3
)
def cancel_expired_booking(booking_no: str) -> dict:
    """到期未支付 → CAS 取消 → 归还单元。

    幂等保证：① CAS（affected_rows==0 直接返回）；② stock_flows 唯一约束防重复归还；
    兜底扫描会与延迟任务重复触发，靠这两层保证安全。
    """
    now_iso = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    session = get_sync_session()
    try:
        booking = session.scalar(select(Booking).where(Booking.booking_no == booking_no))
        if booking is None:
            return {"skipped": "not_found"}
        res: CursorResult = session.execute(  # type: ignore[assignment]
            update(Booking)
            .where(Booking.booking_no == booking_no, Booking.status == "pending_paid")
            .values(status="cancelled", cancelled_at=now_iso, cancel_reason="timeout")
        )
        if res.rowcount != 1:
            # 已被支付或已被取消（延迟任务与兜底扫描并发）——绝不做任何归还
            session.rollback()
            return {"skipped": "state_changed"}
        session.commit()

        items = session.scalars(select(BookingItem).where(BookingItem.booking_no == booking_no)).all()
        slot_ids = [i.court_slot_id for i in items if i.court_slot_id is not None]
        if slot_ids:
            session.execute(
                update(CourtSlot)
                .where(CourtSlot.id.in_(slot_ids), CourtSlot.booking_no == booking_no, CourtSlot.status == "booked")
                .values(status="free", booking_no="")
            )
        # 历史预约项与时段解绑：唯一约束只约束当前有效占用
        session.execute(update(BookingItem).where(BookingItem.booking_no == booking_no).values(court_slot_id=None))
        flow = StockFlow(
            booking_no=booking_no, release_id=booking.release_id, change_type="release", quantity=len(slot_ids)
        )
        session.add(flow)
        session.commit()

        _release_redis(booking.release_id, booking.user_id, slot_ids)
        log.info("booking_cancelled", booking_no=booking_no, reason="timeout", released=len(slot_ids))
        return {"cancelled": booking_no, "released": len(slot_ids)}
    finally:
        session.close()


def _release_redis(release_id: int, user_id: int, slot_ids: list[int]) -> None:
    r = get_sync_redis()
    run_lua_sync(
        r,
        "slot_release.lua",
        [keys.avail_set(release_id), keys.bought_count(user_id, release_id)],
        [len(slot_ids), *[str(i) for i in slot_ids]],
    )
