"""Planning a movement: given a request and a snapshot of current stock, decide exactly what
changes (per-location deltas, frozen valuation, new average cost) or raise a domain error.

These functions never touch the database. The service layer loads the snapshot under a lock,
calls `plan_movement`, and persists the resulting plan in the same transaction.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import AdjustmentReason, MovementType, Unit
from app.domain.errors import (
    AlreadyReversed,
    CannotReverseReversal,
    InsufficientStock,
    RuleViolation,
)
from app.domain.validation import fmt, has_text, validate_quantity, validate_unit_cost
from app.domain.valuation import movement_value, weighted_average_cost


@dataclass(frozen=True)
class MovementRequest:
    """A movement as the domain sees it: quantity is always a positive magnitude and the
    direction is expressed by which location is set."""

    type: MovementType
    quantity: Decimal
    from_location_id: int | None = None
    to_location_id: int | None = None
    unit_cost: Decimal | None = None
    reason_code: AdjustmentReason | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ProductState:
    unit: Unit
    avg_cost: Decimal
    on_hand: Decimal  # total across all locations


@dataclass(frozen=True)
class MovementPlan:
    deltas: dict[int, Decimal]  # location_id -> signed quantity change
    unit_cost: Decimal | None
    value: Decimal | None
    new_avg_cost: Decimal


@dataclass(frozen=True)
class PostedMovement:
    """The parts of an existing movement needed to reverse it."""

    id: int
    type: MovementType
    quantity: Decimal
    from_location_id: int | None
    to_location_id: int | None
    unit_cost: Decimal | None
    reason_code: AdjustmentReason | None
    reverses_movement_id: int | None
    reversed_by_movement_id: int | None


def adjustment_request(
    location_id: int,
    signed_quantity: Decimal,
    reason_code: AdjustmentReason | None,
    note: str | None,
) -> MovementRequest:
    """Turn a signed adjustment (+found / -lost) into a directional request."""
    if not signed_quantity.is_finite() or signed_quantity == 0:
        raise RuleViolation(
            "adjustment quantity must be non-zero (positive adds, negative removes)",
            code="INVALID_QUANTITY",
            field="quantity",
        )
    positive = signed_quantity > 0
    return MovementRequest(
        type=MovementType.ADJUSTMENT,
        quantity=abs(signed_quantity),
        from_location_id=None if positive else location_id,
        to_location_id=location_id if positive else None,
        reason_code=reason_code,
        reason=note,
    )


def reversal_request(original: PostedMovement, reason: str) -> MovementRequest:
    """Rule 1: the correction for a mistaken movement is its exact inverse.

    IN -> OUT (valued at the current average, like any OUT)
    OUT -> IN at the unit cost the OUT was valued at, so the units return at the cost they left
    TRANSFER -> TRANSFER with locations swapped
    ADJUSTMENT -> ADJUSTMENT in the opposite direction, same reason code
    """
    if original.reverses_movement_id is not None:
        raise CannotReverseReversal(
            f"movement {original.id} is itself a reversal and cannot be reversed;"
            " post a new movement instead",
            details={"movement_id": original.id},
        )
    if original.reversed_by_movement_id is not None:
        raise AlreadyReversed(
            f"movement {original.id} was already reversed by movement"
            f" {original.reversed_by_movement_id}",
            details={
                "movement_id": original.id,
                "reversed_by_movement_id": original.reversed_by_movement_id,
            },
        )
    if not has_text(reason):
        raise RuleViolation("a reversal needs a reason", code="REASON_REQUIRED", field="reason")

    inverse_type = {
        MovementType.IN: MovementType.OUT,
        MovementType.OUT: MovementType.IN,
        MovementType.TRANSFER: MovementType.TRANSFER,
        MovementType.ADJUSTMENT: MovementType.ADJUSTMENT,
    }[original.type]
    return MovementRequest(
        type=inverse_type,
        quantity=original.quantity,
        from_location_id=original.to_location_id,
        to_location_id=original.from_location_id,
        unit_cost=original.unit_cost if original.type == MovementType.OUT else None,
        reason_code=original.reason_code,
        reason=reason.strip(),
    )


def plan_movement(
    request: MovementRequest,
    product: ProductState,
    balances: Mapping[int, Decimal],
    *,
    is_reversal: bool = False,
) -> MovementPlan:
    """Validate `request` against business rules and the stock snapshot; return what to write.

    `balances` maps location_id -> current quantity for this product (missing means zero).
    """
    validate_quantity(request.quantity, product.unit)
    _validate_locations(request)
    _validate_type_specific_fields(request, is_reversal)

    qty = request.quantity
    avg = product.avg_cost
    if request.type == MovementType.IN:
        assert request.to_location_id is not None and request.unit_cost is not None
        plan = MovementPlan(
            deltas={request.to_location_id: qty},
            unit_cost=request.unit_cost,
            value=movement_value(qty, request.unit_cost),
            new_avg_cost=weighted_average_cost(product.on_hand, avg, qty, request.unit_cost),
        )
    elif request.type == MovementType.TRANSFER:
        assert request.from_location_id is not None and request.to_location_id is not None
        plan = MovementPlan(
            deltas={request.from_location_id: -qty, request.to_location_id: qty},
            unit_cost=None,
            value=None,
            new_avg_cost=avg,
        )
    else:
        # OUT and ADJUSTMENT (either direction) move stock at the current average cost,
        # which leaves the average itself unchanged.
        if request.to_location_id is not None:
            deltas = {request.to_location_id: qty}
        else:
            assert request.from_location_id is not None
            deltas = {request.from_location_id: -qty}
        plan = MovementPlan(
            deltas=deltas, unit_cost=avg, value=movement_value(qty, avg), new_avg_cost=avg
        )

    ensure_stock_available(balances, plan.deltas)
    return plan


def ensure_stock_available(balances: Mapping[int, Decimal], deltas: Mapping[int, Decimal]) -> None:
    """Rule 3: no location may end below zero."""
    for location_id, delta in deltas.items():
        available = balances.get(location_id, Decimal(0))
        if available + delta < 0:
            raise InsufficientStock(
                f"only {fmt(available)} available at location {location_id},"
                f" cannot remove {fmt(-delta)}",
                details={
                    "location_id": location_id,
                    "available": fmt(available),
                    "requested": fmt(-delta),
                },
            )


def _validate_locations(request: MovementRequest) -> None:
    src, dst = request.from_location_id, request.to_location_id
    expected = {
        MovementType.IN: (False, True),
        MovementType.OUT: (True, False),
        MovementType.TRANSFER: (True, True),
    }
    if request.type == MovementType.ADJUSTMENT:
        valid = (src is None) != (dst is None)
    else:
        valid = ((src is not None), (dst is not None)) == expected[request.type]
    if not valid:
        raise RuleViolation(
            {
                MovementType.IN: "IN needs a destination location and no source",
                MovementType.OUT: "OUT needs a source location and no destination",
                MovementType.TRANSFER: "TRANSFER needs both a source and a destination",
                MovementType.ADJUSTMENT: "ADJUSTMENT applies to exactly one location",
            }[request.type],
            code="INVALID_LOCATIONS",
        )
    if request.type == MovementType.TRANSFER and src == dst:
        raise RuleViolation(
            "source and destination must be different locations",
            code="SAME_LOCATION_TRANSFER",
            field="to_location_id",
        )


def _validate_type_specific_fields(request: MovementRequest, is_reversal: bool) -> None:
    if request.type == MovementType.IN:
        if is_reversal:
            # Returns stock at the (system-computed) cost the OUT left at, which may be Rs 0
            # or carry the full 8-decimal average, so user-input limits do not apply.
            if request.unit_cost is None or request.unit_cost < 0:
                raise RuleViolation("reversal is missing its unit cost", code="INVALID_UNIT_COST")
        else:
            validate_unit_cost(request.unit_cost)
    elif request.unit_cost is not None:
        raise RuleViolation(
            "unit_cost is only accepted on IN movements; other movements are valued"
            " at the current average cost",
            code="UNIT_COST_NOT_ALLOWED",
            field="unit_cost",
        )

    if request.type == MovementType.ADJUSTMENT:
        if request.reason_code is None:
            raise RuleViolation(
                "adjustment needs a reason: "
                + ", ".join(reason.value for reason in AdjustmentReason),
                code="INVALID_ADJUSTMENT_REASON",
                field="reason_code",
            )
        if request.reason_code == AdjustmentReason.OTHER and not has_text(request.reason):
            raise RuleViolation(
                "reason 'other' needs a note explaining the adjustment",
                code="NOTE_REQUIRED",
                field="reason",
            )
    elif request.reason_code is not None:
        raise RuleViolation(
            "reason_code is only used for ADJUSTMENT movements",
            code="REASON_CODE_NOT_ALLOWED",
            field="reason_code",
        )
