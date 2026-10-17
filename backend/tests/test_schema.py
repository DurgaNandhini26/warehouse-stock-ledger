"""Database-level guarantees: exact decimals, immutability triggers and CHECK constraints."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.db.models import Location, Movement, Product, StockBalance
from app.db.types import ScaledDecimal

NOW = datetime(2026, 10, 17, 6, 30, tzinfo=UTC)


def _catalog(session):
    product = Product(sku="P1", name="Rice", unit="kg", reorder_level=Decimal("10"), created_at=NOW)
    loc = Location(code="A-01", description="", created_at=NOW)
    session.add_all([product, loc])
    session.flush()
    return product, loc


def _in_movement(product, loc, **overrides):
    fields = dict(
        type="IN",
        product_id=product.id,
        to_location_id=loc.id,
        quantity=Decimal("5"),
        unit_cost=Decimal("40.5"),
        value=Decimal("202.50"),
        created_at=NOW,
        created_by="tester",
    )
    fields.update(overrides)
    return Movement(**fields)


def test_scaled_decimal_round_trips_exactly(session):
    product, _ = _catalog(session)
    product.avg_cost = Decimal("0.1001")
    session.commit()
    session.expire_all()
    assert session.get(Product, product.id).avg_cost == Decimal("0.1001")


def test_scaled_decimal_refuses_to_silently_round():
    with pytest.raises(ValueError):
        ScaledDecimal(3).process_bind_param(Decimal("1.0005"), None)


def test_timestamps_come_back_timezone_aware_utc(session):
    product, _ = _catalog(session)
    session.commit()
    session.expire_all()
    assert session.get(Product, product.id).created_at == NOW


def test_movement_rows_cannot_be_updated(session):
    product, loc = _catalog(session)
    movement = _in_movement(product, loc)
    session.add(movement)
    session.commit()
    with pytest.raises(DBAPIError, match="immutable"):
        session.execute(update(Movement).values(quantity=Decimal("1")))
    session.rollback()


def test_movement_rows_cannot_be_deleted(session):
    product, loc = _catalog(session)
    session.add(_in_movement(product, loc))
    session.commit()
    with pytest.raises(DBAPIError, match="immutable"):
        session.execute(delete(Movement))
    session.rollback()


def test_cached_balance_can_never_be_negative(session):
    product, loc = _catalog(session)
    session.add(StockBalance(product_id=product.id, location_id=loc.id, quantity=Decimal("-1")))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize(
    "overrides",
    [
        {"unit_cost": Decimal("0")},  # IN must have a positive cost
        {"quantity": Decimal("0")},  # quantity must be positive
        {"from_location_id": 1},  # IN has no source location
        {"type": "OUT"},  # OUT needs a source location, not a destination
        {"type": "ADJUSTMENT"},  # adjustment needs a reason code
    ],
)
def test_movement_check_constraints(session, overrides):
    product, loc = _catalog(session)
    session.add(_in_movement(product, loc, **overrides))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_a_movement_can_be_reversed_only_once(session):
    product, loc = _catalog(session)
    original = _in_movement(product, loc)
    session.add(original)
    session.flush()
    for _ in range(2):
        session.add(
            Movement(
                type="OUT",
                product_id=product.id,
                from_location_id=loc.id,
                quantity=Decimal("5"),
                unit_cost=Decimal("40.5"),
                value=Decimal("202.50"),
                created_at=NOW,
                created_by="tester",
                reverses_movement_id=original.id,
            )
        )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_health_query_works(session):
    assert session.execute(text("SELECT 1")).scalar() == 1
