"""定时维护：兜底扫描、开抢/停约切换、缓存对账。全部幂等。"""

from __future__ import annotations

import datetime as dt
from typing import cast

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.cache.redis_client import get_sync_redis
from app.core.logging import get_logger
from app.db.sync_session import get_sync_session
from app.models import Booking, CourtSlot, Release
from app.tasks.booking_tasks import cancel_expired_booking
from app.tasks.celery_app import celery_app

log = get_logger("courtgate.task.maintenance")


@celery_app.task(name="app.tasks.maintenance_tasks.scan_expired")
def scan_expired() -> dict:
    """兜底扫描：延迟任务可能因 broker 重启丢失，每 5 分钟补投。CAS 保证幂等。"""
    now = dt.datetime.now(dt.UTC)
    threshold = (now - dt.timedelta(minutes=5)).isoformat(timespec="seconds")
    session = get_sync_session()
    try:
        rows = session.scalars(
            select(Booking.booking_no).where(Booking.status == "pending_paid", Booking.expire_at < threshold).limit(500)
        ).all()
        for booking_no in rows:
            cancel_expired_booking.delay(booking_no)
        return {"rescanned": len(rows)}
    finally:
        session.close()


@celery_app.task(name="app.tasks.maintenance_tasks.toggle_releases")
def toggle_releases() -> dict:
    """开抢/停约切换：pending→open（到 open_at），open→closed（过 close_at）。"""
    now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    session = get_sync_session()
    try:
        r1 = cast(
            CursorResult,
            session.execute(
                update(Release).where(Release.status == "pending", Release.open_at <= now).values(status="open")
            ),
        )
        r2 = cast(
            CursorResult,
            session.execute(
                update(Release).where(Release.status == "open", Release.close_at <= now).values(status="closed")
            ),
        )
        session.commit()
        opened, closed = r1.rowcount, r2.rowcount
        if opened or closed:
            log.info("release_status_toggled", opened=opened, closed=closed)
        return {"opened": opened, "closed": closed}
    finally:
        session.close()


@celery_app.task(name="app.tasks.maintenance_tasks.reconcile_all")
def reconcile_all() -> dict:
    """对所有 open 批次做缓存对账，以数据库为准。"""
    session = get_sync_session()
    redis = get_sync_redis()
    try:
        release_ids = session.scalars(select(Release.id).where(Release.status == "open")).all()
        total_drift = 0
        drifted_rids: list[int] = []
        for rid in release_ids:
            db_free = set(
                session.scalars(
                    select(CourtSlot.id).where(CourtSlot.release_id == rid, CourtSlot.status == "free")
                ).all()
            )
            key = f"cg:avail:release:{rid}"
            redis_ids = {int(i) for i in redis.smembers(key)}
            if redis_ids != db_free:
                log.warning("slot_drift_detected", release_id=rid, db=len(db_free), redis=len(redis_ids))
                redis.delete(key)
                if db_free:
                    redis.sadd(key, *[str(i) for i in db_free])
                redis.expire(key, 60 * 60 * 24 * 30)
                from app.core.metrics import slot_drift_total

                slot_drift_total.inc()
                total_drift += 1
                drifted_rids.append(rid)
        if drifted_rids:
            _notify_operators_drift(session, drifted_rids)
        return {"releases": len(release_ids), "drifted": total_drift}
    finally:
        session.close()


def _notify_operators_drift(session: Session, drifted_rids: list[int]) -> None:
    """对账发现漂移即向管理员发站内信告警；同日同批次只告警一次（ref_id 去重）。"""
    from datetime import datetime

    from app.models import Notification, User

    ref_id = f"drift-{datetime.now(dt.UTC):%Y%m%d}-{','.join(map(str, sorted(drifted_rids)))}"
    dup = session.scalar(select(Notification).where(Notification.ref_id == ref_id))
    if dup is not None:
        return
    content = (
        f"对账发现 {len(drifted_rids)} 个批次的可约时段缓存与数据库不一致"
        f"（批次：{sorted(drifted_rids)}），已自动按数据库修正，请关注。"
    )
    operators = session.scalars(select(User).where(User.role == "operator")).all()
    for op in operators:
        session.add(
            Notification(
                user_id=op.id,
                channel="inbox",
                template_code="SYSTEM_ALERT",
                title="缓存一致性告警",
                content=content,
                status="sent",
                ref_type="system",
                ref_id=ref_id,
            )
        )
    session.commit()
