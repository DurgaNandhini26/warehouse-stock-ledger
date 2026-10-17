"""Small helpers so service and API tests read like the business scenario they check."""

from decimal import Decimal

from app.domain.enums import AdjustmentReason, MovementType, Unit
from app.domain.movements import MovementRequest, adjustment_request
from app.services import catalog
from app.services.movements import post_movement

D = Decimal


def make_product(session, sku="RICE-25", unit=Unit.KG, reorder="10"):
    return catalog.create_product(
        session, sku=sku, name=f"{sku} name", unit=unit, reorder_level=D(reorder)
    )


def make_location(session, code="A-01"):
    return catalog.create_location(session, code=code, description=f"bin {code}")


def receive(session, product, location, qty, cost, reference="INV-1"):
    return post_movement(
        session,
        product.id,
        MovementRequest(
            type=MovementType.IN,
            quantity=D(qty),
            to_location_id=location.id,
            unit_cost=D(cost),
        ),
        created_by="tester",
        reference=reference,
    )


def ship(session, product, location, qty, reference="SO-1"):
    return post_movement(
        session,
        product.id,
        MovementRequest(type=MovementType.OUT, quantity=D(qty), from_location_id=location.id),
        created_by="tester",
        reference=reference,
    )


def transfer(session, product, src, dst, qty):
    return post_movement(
        session,
        product.id,
        MovementRequest(
            type=MovementType.TRANSFER,
            quantity=D(qty),
            from_location_id=src.id,
            to_location_id=dst.id,
        ),
        created_by="tester",
    )


def adjust(session, product, location, signed_qty, reason=AdjustmentReason.DAMAGED, note=None):
    return post_movement(
        session,
        product.id,
        adjustment_request(location.id, D(signed_qty), reason, note),
        created_by="tester",
    )
