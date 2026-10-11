"""场馆闭馆/休息日：同场馆同日期唯一；触发时处理受影响预约并通知。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class VenueClosure(Base, IdMixin, TimestampMixin):
    __tablename__ = "venue_closures"
    __table_args__ = (UniqueConstraint("venue_id", "closure_date", name="uk_closures_venue_date"),)

    venue_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("venues.id"), nullable=False, index=True)
    closure_date: Mapped[date] = mapped_column(Date, nullable=False)
    # 自定义通知内容（可空 = 使用默认文案）
    notify_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_bookings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
