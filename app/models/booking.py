"""预约单与明细。三个唯一约束是核心防线。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Booking(Base, IdMixin, TimestampMixin):
    __tablename__ = "bookings"
    __table_args__ = (
        UniqueConstraint("booking_no", name="uk_bookings_no"),
        UniqueConstraint("user_id", "idempotency_key", name="uk_bookings_user_idem"),
    )

    booking_no: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    venue_id: Mapped[int] = mapped_column(Integer, nullable=False)
    release_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    member_discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coupon_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coupon_discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    points_discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending_paid")
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    expire_at: Mapped[str] = mapped_column(String(32), nullable=False)
    paid_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cancelled_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(50), nullable=False, default="")


class BookingItem(Base, IdMixin):
    __tablename__ = "booking_items"
    __table_args__ = (UniqueConstraint("court_slot_id", name="uk_items_court_slot"),)

    booking_no: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 取消/退款后置 NULL：唯一约束只约束当前有效占用，历史行保留展示字段
    court_slot_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    court_id: Mapped[int] = mapped_column(Integer, nullable=False)
    court_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    venue_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    slot_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_label: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)


class StockFlow(Base, IdMixin):
    __tablename__ = "stock_flows"
    __table_args__ = (UniqueConstraint("booking_no", "change_type", name="uk_flows_booking_type"),)

    booking_no: Mapped[str] = mapped_column(String(32), nullable=False)
    release_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
