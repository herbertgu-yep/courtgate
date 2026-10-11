"""密码强度与用户名校验：纯函数单测。"""

import pytest

from app.core.exceptions import UnauthorizedError
from app.core.password import assert_password, password_problems, username_problems


def test_strong_password_passes() -> None:
    assert password_problems("Pass@123") == []


def test_missing_each_requirement() -> None:
    assert "需包含大写字母" in "、".join(password_problems("pass@123"))
    assert "需包含小写字母" in "、".join(password_problems("PASS@123"))
    assert "需包含数字" in "、".join(password_problems("Pass@word"))
    assert "需包含特殊字符" in "、".join(password_problems("Pass1234"))
    assert "长度至少 8 位" in "、".join(password_problems("P@1a"))


def test_too_short() -> None:
    assert len(password_problems("P@1a")) >= 1


def test_assert_raises_with_details() -> None:
    with pytest.raises(UnauthorizedError) as e:
        assert_password("weakpass")
    assert "大写字母" in str(e.value.detail)


def test_username_rules() -> None:
    assert username_problems("admin") == []
    assert username_problems("user_01") == []
    assert username_problems("ab") != []  # 太短
    assert username_problems("带中文用户") != []  # 非字母数字下划线
