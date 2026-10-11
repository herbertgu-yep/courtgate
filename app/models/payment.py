"""支付单。"""

from __future__ import annotations

from sqlalchemy import Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class Payment(Base, IdMixin, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("payment_no", name="uk_payments_no"),
        UniqueConstraint("channel", "third_party_no", name="uk_payments_channel_trade"),
    )

    payment_no: Mapped[str] = mapped_column(String(32), nullable=False)
    booking_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # 可空 + 唯一：MySQL 唯一索引允许多个 NULL，待支付单（尚无第三方流水号）互不冲突
    third_party_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    callback_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    paid_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
