"""精度与定价计算。"""

from app.core.money import bp_multiply, round_half_up


def test_round_half_up_basic() -> None:
    assert round_half_up(0.5) == 1
    assert round_half_up(1.5) == 2
    assert round_half_up(2.5) == 3
    assert round_half_up(-0.5) == -1  # decimal ROUND_HALF_UP：半数远离零方向


def test_round_half_up_not_banker() -> None:
    # Python 内置 round() 是银行家舍入：round(0.5)==0, round(2.5)==2 —— 金额场景禁用
    assert round(0.5) == 0
    assert round_half_up(0.5) == 1
    assert round(2.5) == 2
    assert round_half_up(2.5) == 3


def test_bp_multiply() -> None:
    assert bp_multiply(3000, 15000) == 4500  # 30 元 × 1.5
    assert bp_multiply(3000, 10000) == 3000
    assert bp_multiply(1001, 9500) == 951  # 95 折，四舍五入
    assert bp_multiply(1, 3333) == 0  # 1 分 × 0.3333 → 0
    assert bp_multiply(2, 3333) == 1  # 0.6666 → 1


def test_bp_multiply_member_discount_fifty_cents() -> None:
    # 2250 分 × 95 折 = 2137.5 → 2138（半进位）
    assert bp_multiply(2250, 9500) == 2138
