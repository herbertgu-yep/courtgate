"""时段定义：管理员配置，含价格倍率（基点，15000=1.5倍）。"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class TimeSlot(Base, IdMixin):
    __tablename__ = "time_slots"
    __table_args__ = (UniqueConstraint("release_id", "start_time", name="uk_time_slots_release_start"),)

    # NULL = 全局模板（seed 兼容）；非空 = 该批次的时段切片（按场馆粒度/休息生成）
    release_id: Mapped[int | None] = mapped_column(ForeignKey("releases.id"), nullable=True, index=True)
    start_time: Mapped[str] = mapped_column(Time, nullable=False)
    end_time: Mapped[str] = mapped_column(Time, nullable=False)
    label: Mapped[str] = mapped_column(String(30), nullable=False)
    price_ratio_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
