"""Service layer against a real database: atomicity, concurrency, reversal, reconcile, reports."""

import threading
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.db import repositories as repo
from app.db.models import Movement, StockBalance
from app.db.session import transaction
from app.domain.enums import AdjustmentReason, Unit
from app.domain.errors import (
    AlreadyReversed,
    CannotReverseReversal,
    DuplicateResource,
    InsufficientStock,
    NotFound,
    RuleViolation,
)
from app.services import catalog, reports
from app.services.movements import reverse_movement
from app.services.reconciliation import reconcile
from tests.factories import adjust, make_location, make_product, receive, ship, transfer

D = Decimal


def balance(session, product, location):
    session.expire_all()
    return repo.balances_for(session, product.id, [location.id]).get(location.id, D(0))


def movement_count(session):
    return session.scalar(select(func.count()).select_from(Movement))


@pytest.fixture
def setup(session):
    product = make_product(session)
    a = make_location(session, "A-01")
    b = make_location(session, "B-01")
    return product, a, b


# ---------- basic posting and valuation (rule 5) ----------


def test_in_and_out_update_balance_and_average(session, setup):
    product, a, _ = setup
    receive(session, product, a, "10", "40")
    receive(session, product, a, "30", "60")
    assert balance(session, product, a) == D(40)
    assert catalog.get_product(session, product.id).product.avg_cost == D(55)

    out = ship(session, product, a, "4")
    assert out.unit_cost == D(55) and out.value == D("220.00")
    assert balance(session, product, a) == D(36)


def test_out_value_is_frozen_when_average_changes_later(session, setup):
    product, a, _ = setup
    receive(session, product, a, "10", "40")
    out = ship(session, product, a, "5")
    receive(session, product, a, "5", "100")  # average moves to 70
    session.expire_all()
    stored = repo.get_movement(session, out.id)
    assert stored.unit_cost == D(40) and stored.value == D("200.00")
    assert catalog.get_product(session, product.id).product.avg_cost == D(70)


def test_unknown_product_and_location_are_not_found(session, setup):
    product, a, _ = setup

    class Ghost:
        id = 999

    with pytest.raises(NotFound) as exc:
        receive(session, Ghost, a, "1", "1")
    assert exc.value.code == "PRODUCT_NOT_FOUND"
    with pytest.raises(NotFound) as exc:
        receive(session, product, Ghost, "1", "1")
    assert exc.value.code == "LOCATION_NOT_FOUND"
    assert exc.value.field == "to_location_id"


def test_rule_violation_writes_nothing(session, setup):
    product, a, _ = setup
    with pytest.raises(RuleViolation):
        receive(session, product, a, "5", "0")
    assert movement_count(session) == 0


# ---------- rule 3: never negative ----------


def test_out_beyond_stock_is_rejected_and_nothing_changes(session, setup):
    product, a, _ = setup
    receive(session, product, a, "5", "10")
    with pytest.raises(InsufficientStock):
        ship(session, product, a, "5.001")
    assert balance(session, product, a) == D(5)
    assert movement_count(session) == 1


def test_stock_is_per_location(session, setup):
    product, a, b = setup
    receive(session, product, a, "5", "10")
    with pytest.raises(InsufficientStock):
        ship(session, product, b, "1")


def test_two_outs_racing_for_the_last_units(session_factory, setup):
    product, a, _ = setup
    with session_factory() as s:
        receive(s, product, a, "5", "10")

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker():
        with session_factory() as s:
            barrier.wait()
            try:
                ship(s, product, a, "5")
                outcomes.append("ok")
            except InsufficientStock:
                outcomes.append("rejected")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(outcomes) == ["ok", "rejected"]
    with session_factory() as s:
        assert balance(s, product, a) == D(0)


def test_many_concurrent_outs_never_oversell(session_factory, setup):
    product, a, _ = setup
    with session_factory() as s:
        receive(s, product, a, "5", "10")
    barrier = threading.Barrier(10)
    successes = []

    def worker():
        with session_factory() as s:
            barrier.wait()
            try:
                ship(s, product, a, "1")
                successes.append(1)
            except InsufficientStock:
                pass

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(successes) == 5
    with session_factory() as s:
        assert balance(s, product, a) == D(0)
        assert reconcile(s, repair=False).consistent


# ---------- rule 4: transfer atomicity ----------


def test_transfer_moves_stock_as_one_movement(session, setup):
    product, a, b = setup
    receive(session, product, a, "10", "10")
    before = movement_count(session)
    t = transfer(session, product, a, b, "4")
    assert movement_count(session) == before + 1
    assert (t.from_location_id, t.to_location_id) == (a.id, b.id)
    assert balance(session, product, a) == D(6)
    assert balance(session, product, b) == D(4)
    assert catalog.get_product(session, product.id).on_hand == D(10)


def test_transfer_where_destination_write_fails_midway_rolls_back(session, setup, monkeypatch):
    product, a, b = setup
    receive(session, product, a, "10", "10")
    real_apply = repo.apply_balance_delta

    def failing_apply(s, product_id, location_id, delta):
        if location_id == b.id:
            raise RuntimeError("simulated crash while writing the destination")
        return real_apply(s, product_id, location_id, delta)

    monkeypatch.setattr(repo, "apply_balance_delta", failing_apply)
    with pytest.raises(RuntimeError):
        transfer(session, product, a, b, "4")
    monkeypatch.undo()

    assert balance(session, product, a) == D(10)  # source decrement was rolled back
    assert balance(session, product, b) == D(0)
    assert movement_count(session) == 1  # only the original IN
    assert reconcile(session, repair=False).consistent


# ---------- rule 6: adjustments ----------


def test_adjustments_in_both_directions(session, setup):
    product, a, _ = setup
    receive(session, product, a, "10", "20")
    plus = adjust(session, product, a, "2", AdjustmentReason.COUNT_CORRECTION)
    minus = adjust(session, product, a, "-3", AdjustmentReason.EXPIRED)
    assert plus.to_location_id == a.id and plus.value == D("40.00")
    assert minus.from_location_id == a.id and minus.reason_code == "expired"
    assert balance(session, product, a) == D(9)


def test_other_adjustment_stores_its_note(session, setup):
    product, a, _ = setup
    m = adjust(session, product, a, "1", AdjustmentReason.OTHER, "  sample returned by rep  ")
    assert m.reason == "sample returned by rep"


# ---------- rule 1: reversal ----------


def test_reversal_restores_stock_and_marks_original(session, setup):
    product, a, _ = setup
    receive(session, product, a, "10", "10")
    out = ship(session, product, a, "4")
    reversal = reverse_movement(session, out.id, reason="order cancelled", created_by="sup")

    assert reversal.type == "IN" and reversal.reverses_movement_id == out.id
    assert reversal.unit_cost == out.unit_cost and reversal.value == out.value
    assert reversal.reference == out.reference
    assert balance(session, product, a) == D(10)
    row = repo.get_movement_row(session, out.id)
    assert row.reversed_by_movement_id == reversal.id
    assert row.movement.quantity == D(4)  # original untouched


def test_reversing_an_already_reversed_movement_is_rejected(session, setup):
    product, a, _ = setup
    m = receive(session, product, a, "10", "10")
    reverse_movement(session, m.id, reason="duplicate entry", created_by="sup")
    with pytest.raises(AlreadyReversed):
        reverse_movement(session, m.id, reason="again", created_by="sup")
    assert movement_count(session) == 2


def test_a_reversal_cannot_be_reversed(session, setup):
    product, a, _ = setup
    m = receive(session, product, a, "10", "10")
    r = reverse_movement(session, m.id, reason="duplicate entry", created_by="sup")
    with pytest.raises(CannotReverseReversal):
        reverse_movement(session, r.id, reason="undo the undo", created_by="sup")


def test_reversing_a_receipt_that_was_already_shipped_is_rejected(session, setup):
    product, a, _ = setup
    m = receive(session, product, a, "10", "10")
    ship(session, product, a, "7")
    with pytest.raises(InsufficientStock):
        reverse_movement(session, m.id, reason="wrong supplier", created_by="sup")


def test_reversing_a_transfer_moves_stock_back(session, setup):
    product, a, b = setup
    receive(session, product, a, "10", "10")
    t = transfer(session, product, a, b, "6")
    reverse_movement(session, t.id, reason="wrong bin", created_by="sup")
    assert balance(session, product, a) == D(10)
    assert balance(session, product, b) == D(0)


def test_unknown_movement_cannot_be_reversed(session):
    with pytest.raises(NotFound):
        reverse_movement(session, 12345, reason="x", created_by="sup")


def test_concurrent_reversals_of_the_same_movement(session_factory, setup):
    product, a, _ = setup
    with session_factory() as s:
        m = receive(s, product, a, "10", "10")
    barrier = threading.Barrier(2)
    outcomes = []

    def worker():
        with session_factory() as s:
            barrier.wait()
            try:
                reverse_movement(s, m.id, reason="race", created_by="sup")
                outcomes.append("ok")
            except AlreadyReversed:
                outcomes.append("rejected")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == ["ok", "rejected"]


# ---------- rule 2: reconcile ----------


def test_reconcile_reports_and_repairs_a_corrupted_cache(session, setup):
    product, a, b = setup
    receive(session, product, a, "10", "10")
    transfer(session, product, a, b, "3")
    assert reconcile(session, repair=False).consistent

    with transaction(session):
        repo.set_cached_balance(session, product.id, a.id, D(40))  # floor says 7, cache says 40
        session.delete(session.get(StockBalance, (product.id, b.id)))
        repo.get_product(session, product.id).avg_cost = D(99)

    report = reconcile(session, repair=False)
    assert not report.consistent
    drift = {d.location_code: (d.cached, d.expected, d.difference) for d in report.balance_drift}
    assert drift == {"A-01": (D(40), D(7), D(33)), "B-01": (D(0), D(3), D(-3))}
    assert [(d.cached, d.expected) for d in report.average_cost_drift] == [(D(99), D(10))]
    assert balance(session, product, a) == D(40)  # report-only run changed nothing

    repaired = reconcile(session, repair=True)
    assert repaired.repaired and len(repaired.balance_drift) == 2
    assert balance(session, product, a) == D(7)
    assert balance(session, product, b) == D(3)
    assert reconcile(session, repair=False).consistent


def test_reconcile_replays_average_cost_through_reversals(session, setup):
    product, a, _ = setup
    receive(session, product, a, "10", "10")
    out = ship(session, product, a, "4")
    receive(session, product, a, "4", "40")
    reverse_movement(session, out.id, reason="cancelled", created_by="sup")
    assert reconcile(session, repair=False).consistent


# ---------- rule 7: low stock and reports ----------


def test_low_stock_includes_products_at_or_below_reorder_level(session):
    a = make_location(session)
    at = make_product(session, "AT", reorder="10")
    above = make_product(session, "ABOVE", reorder="10")
    below = make_product(session, "BELOW", reorder="10")
    receive(session, at, a, "10", "1")
    receive(session, above, a, "10.001", "1")
    receive(session, below, a, "2", "1")
    items = {i.product.sku: i for i in reports.low_stock(session)}
    assert set(items) == {"AT", "BELOW"}
    assert items["BELOW"].shortfall == D(8)
    assert items["AT"].shortfall == D(0)


def test_valuation_is_quantity_times_average(session, setup):
    product, a, b = setup
    receive(session, product, a, "3", "33.3333")
    receive(session, product, b, "0.5", "10")
    result = reports.valuation(session)
    line = next(line for line in result.lines if line.product.id == product.id)
    assert line.on_hand == D("3.5")
    # avg = (99.9999 + 5) / 3.5 = 29.99997143 -> value 3.5 * 29.99997143 = 104.9999 -> 105.00
    assert line.value == D("105.00")
    assert result.total_value == D("105.00")


def test_ledger_shows_running_balance(session, setup):
    product, a, b = setup
    receive(session, product, a, "10", "10")
    transfer(session, product, a, b, "4")
    ship(session, product, b, "1")
    ledger = reports.product_ledger(session, product.id, None, limit=50, offset=0)
    assert [(e.quantity_change, e.balance_after) for e in ledger.entries] == [
        (D(10), D(10)),
        (D(0), D(10)),
        (D(-1), D(9)),
    ]
    at_b = reports.product_ledger(session, product.id, b.id, limit=50, offset=0)
    assert [(e.quantity_change, e.balance_after) for e in at_b.entries] == [
        (D(4), D(4)),
        (D(-1), D(3)),
    ]
    assert at_b.closing_balance == D(3)


def test_overview_grid(session, setup):
    product, a, b = setup
    receive(session, product, a, "10", "10")
    transfer(session, product, a, b, "10")
    locations, rows = reports.stock_overview(session)
    assert [loc.code for loc in locations] == ["A-01", "B-01"]
    assert rows[0].quantities == {b.id: D(10)} and rows[0].total == D(10)


# ---------- catalogue ----------


def test_duplicate_sku_is_rejected_case_insensitively(session):
    make_product(session, "rice-25")
    with pytest.raises(DuplicateResource) as exc:
        make_product(session, "RICE-25")
    assert exc.value.code == "DUPLICATE_SKU"


def test_duplicate_location_code_is_rejected(session):
    make_location(session, "a-01")
    with pytest.raises(DuplicateResource):
        make_location(session, "A-01")


def test_reorder_level_rules(session):
    with pytest.raises(RuleViolation) as exc:
        make_product(session, "NEG", reorder="-1")
    assert exc.value.code == "INVALID_REORDER_LEVEL"
    with pytest.raises(RuleViolation):
        catalog.create_product(
            session, sku="BAGS", name="bags", unit=Unit.PCS, reorder_level=D("2.5")
        )
    product = make_product(session, "OK", reorder="0")
    updated = catalog.update_product(session, product.id, reorder_level=D("12.5"), name=" New ")
    assert updated.reorder_level == D("12.5") and updated.name == "New"


def test_update_unknown_product_and_location(session):
    with pytest.raises(NotFound):
        catalog.update_product(session, 404, name="x")
    with pytest.raises(NotFound):
        catalog.update_location(session, 404, description="x")
