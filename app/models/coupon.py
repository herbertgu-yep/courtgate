"""优惠券：模板 + 用户券。领券是限量资源抢占（同预约一个模式）。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class CouponTemplate(Base, IdMixin, TimestampMixin):
    __tablename__ = "coupon_templates"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # fixed=满减 | percent=折扣
    value: Mapped[int] = mapped_column(Integer, nullable=False)  # fixed=减免分；percent=折扣基点(9000=9折)
    min_spend_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_discount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # percent 封顶，0=不限
    total_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    claimed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    per_user_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    valid_from: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    valid_to: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)


class UserCoupon(Base, IdMixin):
    __tablename__ = "user_coupons"
    __table_args__ = (UniqueConstraint("code", name="uk_uc_code"),)

    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    template_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unused", index=True)
    booking_no: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    claimed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expire_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
