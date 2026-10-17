"""Numeric and text rules shared by catalogue and movement code. Each raises RuleViolation."""

from decimal import Decimal

from app.domain.enums import Unit
from app.domain.errors import RuleViolation

MAX_QUANTITY = Decimal("10000000")  # 1 crore units per movement / reorder level
MAX_UNIT_COST = Decimal("10000000")  # Rs 1 crore per unit
QUANTITY_DECIMALS = 3
COST_DECIMALS = 4


def decimal_places(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def fmt(value: Decimal) -> str:
    """Plain string without exponent or trailing zeros, for messages and error details."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _check_quantity_shape(value: Decimal, unit: Unit, field: str, label: str) -> None:
    if value > MAX_QUANTITY:
        raise RuleViolation(
            f"{label} cannot exceed {fmt(MAX_QUANTITY)}", code="INVALID_QUANTITY", field=field
        )
    if decimal_places(value) > QUANTITY_DECIMALS:
        raise RuleViolation(
            f"{label} can have at most {QUANTITY_DECIMALS} decimal places",
            code="INVALID_QUANTITY",
            field=field,
        )
    if unit == Unit.PCS and value != value.to_integral_value():
        raise RuleViolation(
            f"{label} must be a whole number for products counted in pcs",
            code="INVALID_QUANTITY",
            field=field,
        )


def validate_quantity(value: Decimal, unit: Unit, field: str = "quantity") -> None:
    if not value.is_finite() or value <= 0:
        raise RuleViolation(
            "quantity must be greater than zero", code="INVALID_QUANTITY", field=field
        )
    _check_quantity_shape(value, unit, field, "quantity")


def validate_reorder_level(value: Decimal, unit: Unit) -> None:
    if not value.is_finite() or value < 0:
        raise RuleViolation(
            "reorder level cannot be negative", code="INVALID_REORDER_LEVEL", field="reorder_level"
        )
    try:
        _check_quantity_shape(value, unit, "reorder_level", "reorder level")
    except RuleViolation as exc:
        exc.code = "INVALID_REORDER_LEVEL"
        raise


def validate_unit_cost(value: Decimal | None) -> None:
    if value is None or not value.is_finite():
        raise RuleViolation(
            "unit_cost is required for IN movements", code="INVALID_UNIT_COST", field="unit_cost"
        )
    if value <= 0:
        raise RuleViolation(
            "unit_cost must be greater than zero", code="INVALID_UNIT_COST", field="unit_cost"
        )
    if value > MAX_UNIT_COST:
        raise RuleViolation(
            f"unit_cost cannot exceed {fmt(MAX_UNIT_COST)}",
            code="INVALID_UNIT_COST",
            field="unit_cost",
        )
    if decimal_places(value) > COST_DECIMALS:
        raise RuleViolation(
            f"unit_cost can have at most {COST_DECIMALS} decimal places",
            code="INVALID_UNIT_COST",
            field="unit_cost",
        )


def has_text(value: str | None) -> bool:
    return value is not None and value.strip() != ""
