"""金额精度：全项目唯一的舍入入口。金额一律整数分，比率一律基点。"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def round_half_up(value: Decimal | float | int) -> int:
    """四舍五入取整。Python 内置 round() 是银行家舍入（0.5 舍向偶数），金额场景禁用。"""
    d = Decimal(str(value))
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def bp_multiply(amount: int, ratio_bp: int) -> int:
    """amount × ratio_bp / 10000，四舍五入。如 3000 分 × 15000bp = 4500 分。"""
    return round_half_up(Decimal(amount) * Decimal(ratio_bp) / Decimal(10000))
