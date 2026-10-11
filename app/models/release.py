"""放场批次与可约单元（库存挂载点）。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Release(Base, IdMixin, TimestampMixin):
    __tablename__ = "releases"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    venue_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    open_at: Mapped[str] = mapped_column(String(32), nullable=False)  # UTC ISO
    close_at: Mapped[str] = mapped_column(String(32), nullable=False)
    per_user_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", index=True)
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)


class CourtSlot(Base, IdMixin):
    __tablename__ = "court_slots"
    __table_args__ = (UniqueConstraint("court_id", "slot_date", "time_slot_id", name="uk_slots_court_date_time"),)

    release_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    court_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("courts.id"), nullable=False)
    slot_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_slot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("time_slots.id"), nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="free", index=True)
    booking_no: Mapped[str] = mapped_column(String(32), nullable=False, default="")
