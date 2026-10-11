"""JWT 签发与校验。"""

import pytest

from app.core.security import create_access_token, create_refresh_token, decode_token


def test_access_token_roundtrip() -> None:
    t = create_access_token(42)
    assert decode_token(t, expected_type="access") == 42


def test_refresh_token_type_guard() -> None:
    t = create_refresh_token(42)
    with pytest.raises(ValueError):
        decode_token(t, expected_type="access")


def test_garbage_token() -> None:
    with pytest.raises(ValueError):
        decode_token("not.a.token", expected_type="access")


def test_password_hash() -> None:
    from app.core.security import hash_password, verify_password

    h = hash_password("pass1234")
    assert verify_password("pass1234", h)
    assert not verify_password("wrong", h)
