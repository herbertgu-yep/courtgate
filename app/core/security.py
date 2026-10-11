"""密码哈希（bcrypt 直连，不用 passlib）与 JWT 签发/校验。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings

_s = get_settings()


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


def _create_token(user_id: int, ttl: int, token_type: str) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(payload, _s.jwt_secret, algorithm=_s.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    return _create_token(user_id, _s.jwt_access_ttl, "access")


def create_refresh_token(user_id: int) -> str:
    return _create_token(user_id, _s.jwt_refresh_ttl, "refresh")


def decode_token(token: str, *, expected_type: str) -> int:
    """校验并解出 user_id；类型不符或过期均视为无效。"""
    try:
        payload = jwt.decode(token, _s.jwt_secret, algorithms=[_s.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise ValueError("invalid token") from e
    if payload.get("type") != expected_type:
        raise ValueError("wrong token type")
    return int(payload["sub"])
