"""Products and locations. SKU, bin code and unit are fixed after creation (README A3)."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import repositories as repo
from app.db.models import Location, Product
from app.db.session import transaction
from app.domain.enums import Unit
from app.domain.errors import DuplicateResource, NotFound
from app.domain.validation import validate_reorder_level
from app.services.clock import utc_now

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProductView:
    product: Product
    on_hand: Decimal


def create_product(
    session: Session,
    *,
    sku: str,
    name: str,
    unit: Unit,
    reorder_level: Decimal,
    now: datetime | None = None,
) -> Product:
    sku = sku.strip().upper()
    validate_reorder_level(reorder_level, unit)
    with transaction(session):
        if repo.get_product_by_sku(session, sku) is not None:
            raise _duplicate_sku(sku)
        product = Product(
            sku=sku,
            name=name.strip(),
            unit=unit.value,
            reorder_level=reorder_level,
            avg_cost=Decimal(0),
            created_at=now or utc_now(),
        )
        session.add(product)
        try:
            session.flush()
        except IntegrityError as exc:  # lost a race with an identical create
            raise _duplicate_sku(sku) from exc
    log.info("product created", extra={"ctx": {"product_id": product.id, "sku": sku}})
    return product


def update_product(
    session: Session,
    product_id: int,
    *,
    name: str | None = None,
    reorder_level: Decimal | None = None,
) -> Product:
    with transaction(session):
        product = repo.lock_product(session, product_id)
        if product is None:
            raise product_not_found(product_id)
        if reorder_level is not None:
            validate_reorder_level(reorder_level, Unit(product.unit))
            product.reorder_level = reorder_level
        if name is not None:
            product.name = name.strip()
    log.info("product updated", extra={"ctx": {"product_id": product_id}})
    return product


def get_product(session: Session, product_id: int) -> ProductView:
    product = repo.get_product(session, product_id)
    if product is None:
        raise product_not_found(product_id)
    return ProductView(product, repo.total_on_hand(session, product_id))


def list_products(
    session: Session, search: str | None, limit: int, offset: int
) -> tuple[list[ProductView], int]:
    products, total = repo.list_products(session, search, limit, offset)
    totals = repo.totals_by_product(session)
    return [ProductView(p, totals.get(p.id, Decimal(0))) for p in products], total


def create_location(
    session: Session, *, code: str, description: str, now: datetime | None = None
) -> Location:
    code = code.strip().upper()
    with transaction(session):
        if repo.get_location_by_code(session, code) is not None:
            raise _duplicate_location(code)
        location = Location(code=code, description=description.strip(), created_at=now or utc_now())
        session.add(location)
        try:
            session.flush()
        except IntegrityError as exc:
            raise _duplicate_location(code) from exc
    log.info("location created", extra={"ctx": {"location_id": location.id, "code": code}})
    return location


def update_location(session: Session, location_id: int, *, description: str) -> Location:
    with transaction(session):
        location = repo.get_location(session, location_id)
        if location is None:
            raise location_not_found(location_id)
        location.description = description.strip()
    return location


def get_location(session: Session, location_id: int) -> Location:
    location = repo.get_location(session, location_id)
    if location is None:
        raise location_not_found(location_id)
    return location


def list_locations(session: Session, limit: int, offset: int) -> tuple[Sequence[Location], int]:
    return repo.list_locations(session, limit, offset)


def product_not_found(product_id: int) -> NotFound:
    return NotFound(
        f"product {product_id} does not exist",
        code="PRODUCT_NOT_FOUND",
        field="product_id",
        details={"product_id": product_id},
    )


def location_not_found(location_id: int, field: str | None = None) -> NotFound:
    return NotFound(
        f"location {location_id} does not exist",
        code="LOCATION_NOT_FOUND",
        field=field,
        details={"location_id": location_id},
    )


def _duplicate_sku(sku: str) -> DuplicateResource:
    return DuplicateResource(
        f"a product with SKU {sku} already exists", code="DUPLICATE_SKU", field="sku"
    )


def _duplicate_location(code: str) -> DuplicateResource:
    return DuplicateResource(
        f"a location with code {code} already exists", code="DUPLICATE_LOCATION_CODE", field="code"
    )
