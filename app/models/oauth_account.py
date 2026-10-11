"""第三方账号绑定：一个第三方身份只绑一个用户。"""

from __future__ import annotations

from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin


class OAuthAccount(Base, IdMixin):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "openid", name="uk_oauth_provider_openid"),)

    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    openid: Mapped[str] = mapped_column(String(64), nullable=False)
    unionid: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    nickname: Mapped[str] = mapped_column(String(50), nullable=False, default="")
