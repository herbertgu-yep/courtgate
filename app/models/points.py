"""积分账本：流水是权威，users.points_balance 是冗余余额。"""

from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class PointsLedger(Base, IdMixin, TimestampMixin):
    __tablename__ = "points_ledger"
    __table_args__ = (UniqueConstraint("ref_booking_no", "change_type", name="uk_points_booking_type"),)

    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)  # earn|redeem|refund|expire
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # 正=入账，负=出账
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_booking_no: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    remark: Mapped[str] = mapped_column(String(200), nullable=False, default="")
