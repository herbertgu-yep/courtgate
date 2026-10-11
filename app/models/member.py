"""会员等级：按累计消费达标升级，等级给折扣与积分倍率（管理员可配）。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class MemberLevel(Base, IdMixin):
    __tablename__ = "member_levels"
    __table_args__ = (UniqueConstraint("code", name="uk_levels_code"),)

    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    min_spent_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    discount_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    points_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
