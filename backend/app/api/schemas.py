"""Request and response models.

Requests check *shape* only (types, required fields, lengths, absurd digit counts). Business
limits such as "quantity > 0" or "cost has at most 4 decimals" are checked once, in
app/domain, so the rule lives in exactly one place. Decimals are serialised as strings so no
client ever has to parse money through a binary float.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.deps import MAX_ID
from app.domain.enums import AdjustmentReason, MovementType, Unit

T = TypeVar("T")

Id = Annotated[int, Field(ge=1, le=MAX_ID)]
# Rejects NaN/Infinity and absurdly long numbers; real limits are domain rules.
Amount = Annotated[Decimal, Field(max_digits=20, allow_inf_nan=False)]
Who = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
Sku = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$"
    ),
]
BinCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,29}$"
    ),
]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


# ---------- products & locations ----------


class ProductCreate(StrictModel):
    sku: Sku
    name: Name
    unit: Unit
    reorder_level: Amount = Decimal(0)


class ProductUpdate(StrictModel):
    """SKU and unit are deliberately not editable: history is recorded in that unit."""

    name: Name | None = None
    reorder_level: Amount | None = None


class ProductOut(BaseModel):
    id: int
    sku: str
    name: str
    unit: Unit
    reorder_level: Decimal
    avg_cost: Decimal
    on_hand: Decimal
    stock_value: Decimal
    is_low_stock: bool
    created_at: datetime


class LocationCreate(StrictModel):
    code: BinCode
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""


class LocationUpdate(StrictModel):
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class LocationOut(BaseModel):
    id: int
    code: str
    description: str
    created_at: datetime


# ---------- movements ----------


class _MovementBase(StrictModel):
    product_id: Id
    quantity: Amount
    reference: Reference | None = None
    reason: Text500 | None = None
    created_by: Who


class InCreate(_MovementBase):
    type: Literal[MovementType.IN]
    to_location_id: Id
    unit_cost: Amount


class OutCreate(_MovementBase):
    type: Literal[MovementType.OUT]
    from_location_id: Id


class TransferCreate(_MovementBase):
    type: Literal[MovementType.TRANSFER]
    from_location_id: Id
    to_location_id: Id


class AdjustmentCreate(_MovementBase):
    """quantity is signed: positive adds stock to the location, negative removes it."""

    type: Literal[MovementType.ADJUSTMENT]
    location_id: Id
    reason_code: AdjustmentReason


MovementCreate = Annotated[
    InCreate | OutCreate | TransferCreate | AdjustmentCreate, Field(discriminator="type")
]


class ReversalCreate(StrictModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
    created_by: Who


class MovementOut(BaseModel):
    id: int
    type: MovementType
    product_id: int
    sku: str
    from_location_id: int | None
    from_location_code: str | None
    to_location_id: int | None
    to_location_code: str | None
    quantity: Decimal
    unit_cost: Decimal | None
    value: Decimal | None
    reason_code: AdjustmentReason | None
    reason: str | None
    reference: str | None
    created_at: datetime
    created_by: str
    reverses_movement_id: int | None
    reversed_by_movement_id: int | None
    is_reversed: bool


# ---------- balances & reports ----------


class BalanceOut(BaseModel):
    product_id: int
    sku: str
    product_name: str
    unit: Unit
    location_id: int
    location_code: str
    quantity: Decimal


class BalancesOut(BaseModel):
    items: list[BalanceOut]
    total_quantity: Decimal | None = Field(
        description="Sum of quantities; only given when filtered by product (units match)."
    )


class LedgerEntryOut(BaseModel):
    movement: MovementOut
    quantity_change: Decimal
    balance_after: Decimal


class LedgerOut(BaseModel):
    product: ProductOut
    location: LocationOut | None
    entries: list[LedgerEntryOut]
    total: int
    limit: int
    offset: int
    closing_balance: Decimal


class LowStockOut(BaseModel):
    product: ProductOut
    shortfall: Decimal


class ValuationLineOut(BaseModel):
    product_id: int
    sku: str
    name: str
    unit: Unit
    on_hand: Decimal
    avg_cost: Decimal
    value: Decimal


class ValuationOut(BaseModel):
    lines: list[ValuationLineOut]
    total_value: Decimal
    as_of: datetime


class OverviewRowOut(BaseModel):
    product_id: int
    sku: str
    name: str
    unit: Unit
    reorder_level: Decimal
    is_low_stock: bool
    quantities: dict[int, Decimal]
    total: Decimal


class OverviewOut(BaseModel):
    locations: list[LocationOut]
    rows: list[OverviewRowOut]


class BalanceDriftOut(BaseModel):
    product_id: int
    sku: str
    location_id: int
    location_code: str
    cached: Decimal
    expected: Decimal
    difference: Decimal


class AverageCostDriftOut(BaseModel):
    product_id: int
    sku: str
    cached: Decimal
    expected: Decimal


class ReconciliationOut(BaseModel):
    consistent: bool
    repaired: bool
    checked_at: datetime
    balances_checked: int
    products_checked: int
    balance_drift: list[BalanceDriftOut]
    average_cost_drift: list[AverageCostDriftOut]


class MetaOut(BaseModel):
    units: list[Unit]
    movement_types: list[MovementType]
    adjustment_reasons: list[AdjustmentReason]
    reason_requiring_note: AdjustmentReason
    quantity_decimals: int
    unit_cost_decimals: int
    max_quantity: Decimal
    max_unit_cost: Decimal
