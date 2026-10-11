"""场馆与场地：全部由管理员配置，数量不限。"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Venue(Base, IdMixin, TimestampMixin):
    __tablename__ = "venues"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    open_time: Mapped[str] = mapped_column(Time, nullable=False)
    close_time: Mapped[str] = mapped_column(Time, nullable=False)
    # 单次预约时段粒度（分钟），可选 30/60/90/120
    slot_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    # 高峰时段窗口（可空 = 无高峰，全时段按基础价）；peak_ratio_bp 基点，15000 = ×1.5
    peak_start_time: Mapped[str | None] = mapped_column(Time, nullable=True)
    peak_end_time: Mapped[str | None] = mapped_column(Time, nullable=True)
    peak_ratio_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=15000)
    # 中途休息窗口 [{"start":"12:00","end":"13:30"}]，生成时段时跳过
    breaks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notice: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    __table_args__ = ({"comment": "场馆"},)


class Court(Base, IdMixin, TimestampMixin):
    __tablename__ = "courts"

    venue_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    court_type: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    base_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
