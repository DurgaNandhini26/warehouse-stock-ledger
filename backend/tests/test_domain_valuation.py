"""Rule 5: weighted average cost, and the rounding policy for money."""

from decimal import Decimal
from fractions import Fraction

import pytest

from app.domain.valuation import movement_value, weighted_average_cost

D = Decimal


def test_first_receipt_sets_average_to_its_cost():
    assert weighted_average_cost(D(0), D(0), D(10), D("42.50")) == D("42.5000")


def test_average_is_weighted_by_quantity():
    # 10 @ 40 + 30 @ 60 = 2200 / 40 = 55
    assert weighted_average_cost(D(10), D(40), D(30), D(60)) == D("55.0000")


def test_average_is_rounded_half_even_to_eight_places():
    # (1 * 1 + 2 * 2) / 3 = 1.666666666... -> 1.66666667
    assert weighted_average_cost(D(1), D(1), D(2), D(2)) == D("1.66666667")
    # exact midpoint 0.000000005 rounds to even
    assert weighted_average_cost(D(1), D("0.00000001"), D(1), D(0)) == D("0")


def test_receiving_into_empty_stock_ignores_stale_average():
    assert weighted_average_cost(D(0), D("999"), D(5), D(10)) == D("10.0000")


def test_rounding_error_stays_bounded_after_many_receipts():
    """1,000 receipts at awkward prices: cached average stays within 0.000001 of the exact value.

    With 4-decimal rounding this drifted by 0.00033, i.e. visible in the 4th decimal place."""
    on_hand, avg = D(0), D(0)
    exact_value, exact_qty = Fraction(0), Fraction(0)
    for i in range(1000):
        qty = D(i % 7 + 1)
        cost = D(f"{(i * 37) % 101 + 1}.{i % 97:02d}")
        avg = weighted_average_cost(on_hand, avg, qty, cost)
        on_hand += qty
        exact_value += Fraction(qty) * Fraction(cost)
        exact_qty += Fraction(qty)
    exact_avg = exact_value / exact_qty
    assert abs(Fraction(avg) - exact_avg) <= Fraction(1, 1_000_000)


def test_movement_value_rounds_to_paise():
    assert movement_value(D("3"), D("33.3333")) == D("100.00")
    assert movement_value(D("0.001"), D("4.9999")) == D("0.00")
    assert movement_value(D("1.5"), D("10.0050")) == D("15.01")  # 15.0075 -> 15.01


@pytest.mark.parametrize(
    ("on_hand", "incoming"),
    [(D(-1), D(1)), (D(0), D(0)), (D(1), D(-1))],
)
def test_weighted_average_rejects_impossible_inputs(on_hand, incoming):
    with pytest.raises(ValueError):
        weighted_average_cost(on_hand, D(1), incoming, D(1))
