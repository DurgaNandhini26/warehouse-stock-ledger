"""Rules 1, 3, 4, 5, 6 as pure functions: planning a movement against a snapshot of stock."""

from decimal import Decimal

import pytest

from app.domain.enums import AdjustmentReason, MovementType, Unit
from app.domain.errors import (
    AlreadyReversed,
    CannotReverseReversal,
    InsufficientStock,
    RuleViolation,
)
from app.domain.movements import (
    MovementRequest,
    PostedMovement,
    ProductState,
    adjustment_request,
    plan_movement,
    reversal_request,
)

D = Decimal
A, B = 1, 2  # location ids
KG = ProductState(unit=Unit.KG, avg_cost=D("50.0000"), on_hand=D("10"))
PCS = ProductState(unit=Unit.PCS, avg_cost=D("8.0000"), on_hand=D("20"))


def req(type_, qty, **kw):
    return MovementRequest(type=MovementType(type_), quantity=D(qty), **kw)


def codes(exc_info):
    return exc_info.value.code


# ---------- IN ----------


def test_in_adds_stock_and_updates_average():
    plan = plan_movement(req("IN", "10", to_location_id=A, unit_cost=D("70")), KG, {A: D(10)})
    assert plan.deltas == {A: D(10)}
    assert plan.unit_cost == D("70")
    assert plan.value == D("700.00")
    assert plan.new_avg_cost == D("60.0000")


@pytest.mark.parametrize("cost", ["0", "-1", "-0.0001"])
def test_in_rejects_zero_or_negative_cost(cost):
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("IN", "1", to_location_id=A, unit_cost=D(cost)), KG, {})
    assert codes(exc) == "INVALID_UNIT_COST"
    assert exc.value.field == "unit_cost"


def test_in_accepts_smallest_positive_cost():
    plan = plan_movement(req("IN", "1", to_location_id=A, unit_cost=D("0.0001")), KG, {})
    assert plan.unit_cost == D("0.0001")


def test_in_rejects_cost_with_more_than_four_decimals():
    with pytest.raises(RuleViolation):
        plan_movement(req("IN", "1", to_location_id=A, unit_cost=D("1.00001")), KG, {})


def test_in_rejects_cost_above_maximum():
    with pytest.raises(RuleViolation):
        plan_movement(req("IN", "1", to_location_id=A, unit_cost=D("10000000.0001")), KG, {})


def test_in_requires_cost():
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("IN", "1", to_location_id=A), KG, {})
    assert codes(exc) == "INVALID_UNIT_COST"


def test_in_requires_destination_only():
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("IN", "1", from_location_id=A, unit_cost=D(1)), KG, {})
    assert codes(exc) == "INVALID_LOCATIONS"


# ---------- quantity boundaries (all types share them) ----------


@pytest.mark.parametrize("qty", ["0", "-0.001", "-5"])
def test_quantity_must_be_positive(qty):
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("IN", qty, to_location_id=A, unit_cost=D(1)), KG, {})
    assert codes(exc) == "INVALID_QUANTITY"


def test_quantity_smallest_step_for_kg_is_one_gram():
    plan = plan_movement(req("IN", "0.001", to_location_id=A, unit_cost=D(1)), KG, {})
    assert plan.deltas == {A: D("0.001")}
    with pytest.raises(RuleViolation):
        plan_movement(req("IN", "0.0005", to_location_id=A, unit_cost=D(1)), KG, {})


def test_pieces_must_be_whole_numbers():
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("IN", "1.5", to_location_id=A, unit_cost=D(1)), PCS, {})
    assert codes(exc) == "INVALID_QUANTITY"
    plan = plan_movement(req("IN", "1", to_location_id=A, unit_cost=D(1)), PCS, {})
    assert plan.deltas == {A: D(1)}


def test_quantity_maximum_boundary():
    ok = req("IN", "10000000", to_location_id=A, unit_cost=D(1))
    assert plan_movement(ok, KG, {}).deltas == {A: D("10000000")}
    with pytest.raises(RuleViolation):
        plan_movement(req("IN", "10000000.001", to_location_id=A, unit_cost=D(1)), KG, {})


# ---------- OUT (rule 3 + rule 5) ----------


def test_out_is_valued_at_current_average_and_keeps_average():
    plan = plan_movement(req("OUT", "4", from_location_id=A), KG, {A: D(10)})
    assert plan.deltas == {A: D(-4)}
    assert plan.unit_cost == D("50.0000")
    assert plan.value == D("200.00")
    assert plan.new_avg_cost == D("50.0000")


def test_out_of_exactly_the_available_quantity_is_allowed():
    plan = plan_movement(req("OUT", "10", from_location_id=A), KG, {A: D(10)})
    assert plan.deltas == {A: D(-10)}


def test_out_one_gram_more_than_available_is_rejected():
    with pytest.raises(InsufficientStock) as exc:
        plan_movement(req("OUT", "10.001", from_location_id=A), KG, {A: D(10)})
    assert exc.value.details == {
        "location_id": A,
        "available": "10",
        "requested": "10.001",
    }


def test_out_from_a_location_with_no_stock_row_is_rejected():
    with pytest.raises(InsufficientStock):
        plan_movement(req("OUT", "1", from_location_id=B), KG, {A: D(10)})


def test_out_rejects_unit_cost():
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("OUT", "1", from_location_id=A, unit_cost=D(5)), KG, {A: D(10)})
    assert codes(exc) == "UNIT_COST_NOT_ALLOWED"


def test_out_requires_source_only():
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("OUT", "1", to_location_id=A), KG, {A: D(10)})
    assert codes(exc) == "INVALID_LOCATIONS"


# ---------- TRANSFER (rule 4) ----------


def test_transfer_moves_between_two_locations_without_valuation():
    plan = plan_movement(req("TRANSFER", "3", from_location_id=A, to_location_id=B), KG, {A: D(10)})
    assert plan.deltas == {A: D(-3), B: D(3)}
    assert plan.unit_cost is None
    assert plan.value is None
    assert plan.new_avg_cost == KG.avg_cost


def test_transfer_to_the_same_location_is_rejected():
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("TRANSFER", "1", from_location_id=A, to_location_id=A), KG, {A: D(9)})
    assert codes(exc) == "SAME_LOCATION_TRANSFER"


def test_transfer_cannot_overdraw_the_source():
    with pytest.raises(InsufficientStock):
        plan_movement(
            req("TRANSFER", "10.001", from_location_id=A, to_location_id=B), KG, {A: D(10)}
        )


def test_transfer_needs_both_locations():
    with pytest.raises(RuleViolation):
        plan_movement(req("TRANSFER", "1", from_location_id=A), KG, {A: D(10)})


# ---------- ADJUSTMENT (rule 6) ----------


def test_positive_adjustment_adds_stock_at_average_cost():
    request = adjustment_request(A, D("2"), AdjustmentReason.COUNT_CORRECTION, None)
    assert request.to_location_id == A and request.from_location_id is None
    plan = plan_movement(request, KG, {A: D(10)})
    assert plan.deltas == {A: D(2)}
    assert plan.value == D("100.00")
    assert plan.new_avg_cost == KG.avg_cost


def test_negative_adjustment_removes_stock():
    request = adjustment_request(A, D("-3"), AdjustmentReason.DAMAGED, None)
    assert request.from_location_id == A and request.quantity == D(3)
    assert plan_movement(request, KG, {A: D(10)}).deltas == {A: D(-3)}


def test_negative_adjustment_cannot_go_below_zero():
    request = adjustment_request(A, D("-10.001"), AdjustmentReason.THEFT, None)
    with pytest.raises(InsufficientStock):
        plan_movement(request, KG, {A: D(10)})


def test_zero_adjustment_is_rejected():
    with pytest.raises(RuleViolation) as exc:
        adjustment_request(A, D("0"), AdjustmentReason.DAMAGED, None)
    assert codes(exc) == "INVALID_QUANTITY"


def test_adjustment_requires_a_reason_from_the_list():
    with pytest.raises(RuleViolation) as exc:
        plan_movement(req("ADJUSTMENT", "1", to_location_id=A), KG, {})
    assert codes(exc) == "INVALID_ADJUSTMENT_REASON"


@pytest.mark.parametrize("note", [None, "", "   "])
def test_other_reason_requires_a_note(note):
    request = adjustment_request(A, D("1"), AdjustmentReason.OTHER, note)
    with pytest.raises(RuleViolation) as exc:
        plan_movement(request, KG, {})
    assert codes(exc) == "NOTE_REQUIRED"


def test_other_reason_with_note_is_accepted():
    request = adjustment_request(A, D("1"), AdjustmentReason.OTHER, "found behind rack")
    assert plan_movement(request, KG, {}).deltas == {A: D(1)}


def test_reason_code_is_only_for_adjustments():
    with pytest.raises(RuleViolation):
        plan_movement(
            req("OUT", "1", from_location_id=A, reason_code=AdjustmentReason.THEFT),
            KG,
            {A: D(5)},
        )


# ---------- reversal (rule 1) ----------


def posted(type_, **kw):
    defaults = dict(
        id=7,
        type=MovementType(type_),
        quantity=D(4),
        from_location_id=None,
        to_location_id=None,
        unit_cost=None,
        reason_code=None,
        reverses_movement_id=None,
        reversed_by_movement_id=None,
    )
    defaults.update(kw)
    return PostedMovement(**defaults)


def test_reversing_an_in_removes_the_stock_as_an_out():
    request = reversal_request(posted("IN", to_location_id=A, unit_cost=D(30)), "keyed twice")
    assert request.type == MovementType.OUT
    assert request.from_location_id == A and request.to_location_id is None
    assert request.unit_cost is None


def test_reversing_an_out_returns_stock_at_the_cost_it_left_at():
    request = reversal_request(posted("OUT", from_location_id=A, unit_cost=D(45)), "wrong order")
    assert request.type == MovementType.IN
    assert request.to_location_id == A
    assert request.unit_cost == D(45)


def test_reversing_a_transfer_swaps_locations():
    request = reversal_request(
        posted("TRANSFER", from_location_id=A, to_location_id=B), "wrong bin"
    )
    assert (request.type, request.from_location_id, request.to_location_id) == (
        MovementType.TRANSFER,
        B,
        A,
    )


def test_reversing_an_adjustment_flips_direction_and_keeps_reason_code():
    original = posted(
        "ADJUSTMENT", from_location_id=A, unit_cost=D(5), reason_code=AdjustmentReason.DAMAGED
    )
    request = reversal_request(original, "bags were fine")
    assert request.to_location_id == A and request.from_location_id is None
    assert request.reason_code == AdjustmentReason.DAMAGED


def test_reversal_of_an_out_valued_at_zero_is_allowed():
    request = reversal_request(posted("OUT", from_location_id=A, unit_cost=D(0)), "undo")
    plan = plan_movement(request, KG, {}, is_reversal=True)
    assert plan.deltas == {A: D(4)}


def test_reversal_of_an_out_keeps_its_full_precision_cost():
    request = reversal_request(
        posted("OUT", from_location_id=A, unit_cost=D("33.33333333")), "undo"
    )
    plan = plan_movement(request, KG, {}, is_reversal=True)
    assert plan.unit_cost == D("33.33333333")
    assert plan.value == D("133.33")


def test_reversing_an_already_reversed_movement_is_rejected():
    with pytest.raises(AlreadyReversed):
        reversal_request(posted("IN", to_location_id=A, reversed_by_movement_id=9), "again")


def test_a_reversal_cannot_itself_be_reversed():
    with pytest.raises(CannotReverseReversal):
        reversal_request(posted("OUT", from_location_id=A, reverses_movement_id=3), "undo undo")


@pytest.mark.parametrize("reason", ["", "  "])
def test_reversal_requires_a_reason(reason):
    with pytest.raises(RuleViolation) as exc:
        reversal_request(posted("IN", to_location_id=A), reason)
    assert codes(exc) == "REASON_REQUIRED"


def test_reversing_an_in_whose_stock_was_already_shipped_is_rejected():
    request = reversal_request(posted("IN", to_location_id=A, quantity=D(10)), "dup")
    with pytest.raises(InsufficientStock):
        plan_movement(request, KG, {A: D(6)}, is_reversal=True)
