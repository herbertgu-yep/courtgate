"""定价引擎：纯函数，不碰 DB/Redis——可被完整单测。

叠加顺序固定：会员折扣 → 优惠券 → 积分抵扣。顺序不同结果不同。
所有金额整数分；会员/券的折扣用基点；半进位舍入唯一入口在 core.money。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.money import bp_multiply


@dataclass(frozen=True)
class CouponView:
    type: str  # fixed | percent
    value: int  # fixed=减免分；percent=折扣基点(9000=9折)
    min_spend_cents: int = 0
    max_discount_cents: int = 0


@dataclass(frozen=True)
class Quote:
    subtotal_cents: int
    member_discount_cents: int
    coupon_discount_cents: int
    points_used: int
    points_discount_cents: int
    total_cents: int


def quote(
    *,
    subtotal_cents: int,
    member_discount_bp: int = 10000,
    coupon: CouponView | None = None,
    use_points: int = 0,
    user_points: int = 0,
    points_redeem_max_bp: int = 5000,
) -> Quote:
    subtotal = subtotal_cents
    # 1) 会员折扣
    after_member = bp_multiply(subtotal, member_discount_bp)
    member_discount = subtotal - after_member
    # 2) 优惠券（门槛按原价小计判定，不按折后价——避免折扣互相蚕食）
    coupon_discount = 0
    if coupon is not None and subtotal >= coupon.min_spend_cents:
        if coupon.type == "fixed":
            coupon_discount = min(coupon.value, after_member)
        else:  # percent
            d = bp_multiply(after_member, 10000 - coupon.value)
            if coupon.max_discount_cents:
                d = min(d, coupon.max_discount_cents)
            coupon_discount = d
    after_coupon = max(0, after_member - coupon_discount)
    # 3) 积分抵扣：1 积分 = 1 分，上限 = 折后价 × redeem_max_bp
    max_by_ratio = after_coupon * points_redeem_max_bp // 10000
    points_used = max(0, min(use_points, user_points, max_by_ratio))
    total = after_coupon - points_used
    return Quote(subtotal, member_discount, coupon_discount, points_used, points_used, total)
