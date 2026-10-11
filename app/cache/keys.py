"""Redis 键构造：业务代码禁止手写键字符串。"""

from __future__ import annotations


def avail_set(release_id: int) -> str:
    return f"cg:avail:release:{release_id}"


def bought_count(user_id: int, release_id: int) -> str:
    return f"cg:booked:user:{user_id}:release:{release_id}"


def idem(user_id: int, key: str) -> str:
    return f"cg:idem:{user_id}:{key}"


def rate_limit_user(user_id: int) -> str:
    return f"cg:rl:user:{user_id}"


def rate_limit_ip(ip: str) -> str:
    return f"cg:rl:ip:{ip}"


def oauth_ticket(ticket: str) -> str:
    return f"cg:oauth:ticket:{ticket}"


def slots_view(release_id: int) -> str:
    """选时段页的静态骨架（日期/场地/时段/价格），可用性每请求现算。"""
    return f"cg:slotview:{release_id}"


def depleted(release_id: int) -> str:
    """售罄标记：集合删空后防止反复回源重建。"""
    return f"cg:avail:release:{release_id}:depleted"


def coupon_stock(template_id: int) -> str:
    return f"cg:couponstock:tpl:{template_id}"


def coupon_claimed(template_id: int, user_id: int) -> str:
    return f"cg:couponclaimed:{template_id}:{user_id}"


def captcha(captcha_id: str) -> str:
    return f"cg:captcha:{captcha_id}"
