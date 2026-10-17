"""Turn service results into response models. Pure formatting, no decisions."""

from decimal import Decimal

from app.api import schemas
from app.db.models import Location, Product
from app.db.repositories import MovementRow
from app.domain.valuation import movement_value


def product_out(product: Product, on_hand: Decimal) -> schemas.ProductOut:
    return schemas.ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        unit=product.unit,
        reorder_level=product.reorder_level,
        avg_cost=product.avg_cost,
        on_hand=on_hand,
        stock_value=movement_value(on_hand, product.avg_cost),
        is_low_stock=on_hand <= product.reorder_level,
        created_at=product.created_at,
    )


def location_out(location: Location) -> schemas.LocationOut:
    return schemas.LocationOut(
        id=location.id,
        code=location.code,
        description=location.description,
        created_at=location.created_at,
    )


def movement_out(row: MovementRow) -> schemas.MovementOut:
    m = row.movement
    return schemas.MovementOut(
        id=m.id,
        type=m.type,
        product_id=m.product_id,
        sku=row.sku,
        from_location_id=m.from_location_id,
        from_location_code=row.from_location_code,
        to_location_id=m.to_location_id,
        to_location_code=row.to_location_code,
        quantity=m.quantity,
        unit_cost=m.unit_cost,
        value=m.value,
        reason_code=m.reason_code,
        reason=m.reason,
        reference=m.reference,
        created_at=m.created_at,
        created_by=m.created_by,
        reverses_movement_id=m.reverses_movement_id,
        reversed_by_movement_id=row.reversed_by_movement_id,
        is_reversed=row.reversed_by_movement_id is not None,
    )
