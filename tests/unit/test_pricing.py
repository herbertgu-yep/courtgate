"""定价引擎：叠加顺序与边界。"""

from app.services.pricing.engine import CouponView, quote


def test_no_discounts() -> None:
    q = quote(subtotal_cents=9000)
    assert q.total_cents == 9000 and q.member_discount_cents == 0


def test_member_discount_only() -> None:
    q = quote(subtotal_cents=9000, member_discount_bp=9500)
    assert q.member_discount_cents == 450 and q.total_cents == 8550


def test_fixed_coupon_threshold_by_subtotal() -> None:
    """门槛按原价小计判定：小计 100 元、门槛 50 元 → 可用。"""
    c = CouponView(type="fixed", value=1000, min_spend_cents=5000)
    q = quote(subtotal_cents=10000, member_discount_bp=10000, coupon=c)
    assert q.coupon_discount_cents == 1000 and q.total_cents == 9000


def test_fixed_coupon_never_negative() -> None:
    """券面额超过订单金额 → 金额不为负。"""
    c = CouponView(type="fixed", value=50000, min_spend_cents=0)
    q = quote(subtotal_cents=10000, coupon=c)
    assert q.total_cents == 0


def test_percent_coupon_with_cap() -> None:
    c = CouponView(type="percent", value=9000, max_discount_cents=500)  # 9 折、封顶 5 元
    q = quote(subtotal_cents=10000, coupon=c)
    assert q.coupon_discount_cents == 500  # 10000×10%=1000 但封顶 500


def test_points_capped_by_ratio() -> None:
    """积分抵扣上限 50%（5000bp），且不超过用户持有。"""
    q = quote(subtotal_cents=10000, use_points=9999, user_points=9999, points_redeem_max_bp=5000)
    assert q.points_used == 5000 and q.total_cents == 5000


def test_points_limited_by_user_balance() -> None:
    q = quote(subtotal_cents=10000, use_points=999, user_points=500, points_redeem_max_bp=5000)
    assert q.points_used == 500


def test_full_stack_order_matters() -> None:
    """顺序固定：会员 → 券 → 积分。900 元小计、95 折、满 500 减 100、用 200 积分。"""
    c = CouponView(type="fixed", value=10000, min_spend_cents=50000)
    q = quote(
        subtotal_cents=90000,
        member_discount_bp=9500,
        coupon=c,
        use_points=200,
        user_points=200,
        points_redeem_max_bp=5000,
    )
    # 90000 → 95 折 85500 → 券减 10000 → 75500 → 积分 200 → 75300
    assert (q.subtotal_cents, q.member_discount_cents, q.coupon_discount_cents, q.points_used, q.total_cents) == (
        90000,
        4500,
        10000,
        200,
        75300,
    )
