"""密码强度与用户名合法性校验：纯函数，可完整单测。

密码规则（注册时校验，登录不重复校验）：
- 长度 8~64 位
- 必须同时包含：大写字母、小写字母、数字、特殊字符
用户名规则：4~20 位，字母 / 数字 / 下划线。
"""

from __future__ import annotations

import re

from app.core.exceptions import UnauthorizedError

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,20}$")
_SPECIAL_RE = re.compile(r"[!@#$%^&*()_+\-=\[\]{};':\",.<>/?\\|~`]")


def password_problems(password: str) -> list[str]:
    """返回密码不满足的规则列表；空列表 = 合格。"""
    problems: list[str] = []
    if len(password) < 8:
        problems.append("长度至少 8 位")
    if not re.search(r"[A-Z]", password):
        problems.append("需包含大写字母")
    if not re.search(r"[a-z]", password):
        problems.append("需包含小写字母")
    if not re.search(r"\d", password):
        problems.append("需包含数字")
    if not _SPECIAL_RE.search(password):
        problems.append("需包含特殊字符")
    return problems


def username_problems(username: str) -> list[str]:
    if not _USERNAME_RE.match(username):
        return ["用户名须为 4~20 位字母、数字或下划线"]
    return []


def assert_password(password: str) -> None:
    """不合格直接抛 401（携带缺失项明细，前端可逐条提示）。"""

    problems = password_problems(password)
    if problems:
        raise UnauthorizedError("密码强度不足：" + "、".join(problems))


def assert_username(username: str) -> None:

    problems = username_problems(username)
    if problems:
        raise UnauthorizedError("、".join(problems))
