"""Rule 5: weighted average cost.

Policy (README assumption A6):
- Average cost is kept to 8 decimal places internally, rounded half-even. An earlier version
  kept 4 places and the cached average drifted by ~0.0003 from the exact value after 1,000
  receipts (see tests/test_domain_valuation.py); 8 places keeps the drift below 0.000001.
- Purchase costs entered by users are limited to 4 decimal places (validation.py).
- Money totals (movement value, stock value) are rounded half-even to 2 places (paise).
"""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext

COST_STEP = Decimal("0.00000001")
VALUE_STEP = Decimal("0.01")


def weighted_average_cost(
    on_hand: Decimal, current_avg: Decimal, incoming_qty: Decimal, incoming_unit_cost: Decimal
) -> Decimal:
    """New average after receiving `incoming_qty` units at `incoming_unit_cost`."""
    if on_hand < 0:
        raise ValueError("on-hand quantity cannot be negative")
    if incoming_qty <= 0:
        raise ValueError("incoming quantity must be positive")
    with localcontext() as ctx:
        ctx.prec = 40
        total_value = on_hand * current_avg + incoming_qty * incoming_unit_cost
        average = total_value / (on_hand + incoming_qty)
        return average.quantize(COST_STEP, rounding=ROUND_HALF_EVEN)


def movement_value(quantity: Decimal, unit_cost: Decimal) -> Decimal:
    """Rupee value of `quantity` units at `unit_cost`, rounded to paise."""
    with localcontext() as ctx:
        ctx.prec = 40
        return (quantity * unit_cost).quantize(VALUE_STEP, rounding=ROUND_HALF_EVEN)
