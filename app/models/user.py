"""用户：用户名密码登录，角色 customer / operator。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    # 联系手机号（选填，登录后引导补充；闭馆退款等场景便于联系）
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    member_level: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    total_spent_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    points_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
