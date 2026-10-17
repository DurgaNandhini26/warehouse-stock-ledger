from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api import schemas
from app.api.deps import IdPath, Limit, Offset, SessionDep
from app.api.presenters import location_out, product_out
from app.domain.enums import AdjustmentReason, MovementType, Unit
from app.domain.validation import (
    COST_DECIMALS,
    MAX_QUANTITY,
    MAX_UNIT_COST,
    QUANTITY_DECIMALS,
)
from app.services import catalog

router = APIRouter()


@router.get("/meta", response_model=schemas.MetaOut, tags=["meta"])
def get_meta() -> schemas.MetaOut:
    """Enumerations and limits, so the UI never hard-codes business lists."""
    return schemas.MetaOut(
        units=list(Unit),
        movement_types=list(MovementType),
        adjustment_reasons=list(AdjustmentReason),
        reason_requiring_note=AdjustmentReason.OTHER,
        quantity_decimals=QUANTITY_DECIMALS,
        unit_cost_decimals=COST_DECIMALS,
        max_quantity=MAX_QUANTITY,
        max_unit_cost=MAX_UNIT_COST,
    )


@router.get("/products", response_model=schemas.Page[schemas.ProductOut], tags=["products"])
def list_products(
    session: SessionDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    limit: Limit = 50,
    offset: Offset = 0,
):
    views, total = catalog.list_products(session, search, limit, offset)
    return schemas.Page(
        items=[product_out(v.product, v.on_hand) for v in views],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/products",
    response_model=schemas.ProductOut,
    status_code=status.HTTP_201_CREATED,
    tags=["products"],
)
def create_product(body: schemas.ProductCreate, session: SessionDep):
    product = catalog.create_product(
        session,
        sku=body.sku,
        name=body.name,
        unit=body.unit,
        reorder_level=body.reorder_level,
    )
    return product_out(product, Decimal(0))


@router.get("/products/{product_id}", response_model=schemas.ProductOut, tags=["products"])
def get_product(product_id: IdPath, session: SessionDep):
    view = catalog.get_product(session, product_id)
    return product_out(view.product, view.on_hand)


@router.patch("/products/{product_id}", response_model=schemas.ProductOut, tags=["products"])
def update_product(product_id: IdPath, body: schemas.ProductUpdate, session: SessionDep):
    catalog.update_product(session, product_id, name=body.name, reorder_level=body.reorder_level)
    view = catalog.get_product(session, product_id)
    return product_out(view.product, view.on_hand)


@router.get("/locations", response_model=schemas.Page[schemas.LocationOut], tags=["locations"])
def list_locations(session: SessionDep, limit: Limit = 50, offset: Offset = 0):
    locations, total = catalog.list_locations(session, limit, offset)
    return schemas.Page(
        items=[location_out(loc) for loc in locations], total=total, limit=limit, offset=offset
    )


@router.post(
    "/locations",
    response_model=schemas.LocationOut,
    status_code=status.HTTP_201_CREATED,
    tags=["locations"],
)
def create_location(body: schemas.LocationCreate, session: SessionDep):
    return location_out(
        catalog.create_location(session, code=body.code, description=body.description)
    )


@router.get("/locations/{location_id}", response_model=schemas.LocationOut, tags=["locations"])
def get_location(location_id: IdPath, session: SessionDep):
    return location_out(catalog.get_location(session, location_id))


@router.patch("/locations/{location_id}", response_model=schemas.LocationOut, tags=["locations"])
def update_location(location_id: IdPath, body: schemas.LocationUpdate, session: SessionDep):
    return location_out(catalog.update_location(session, location_id, description=body.description))
