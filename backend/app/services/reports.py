"""Read-side use-cases: balances, ledger (running balance), low stock, valuation, overview."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db import repositories as repo
from app.db.models import Location, Product
from app.db.repositories import MovementRow
from app.domain.valuation import movement_value
from app.services.catalog import get_location, get_product
from app.services.clock import utc_now

ZERO = Decimal(0)


# ---------- ledger ----------


@dataclass(frozen=True)
class LedgerEntry:
    row: MovementRow
    quantity_change: Decimal  # effect on the balance being followed
    balance_after: Decimal


@dataclass(frozen=True)
class Ledger:
    product: Product
    location: Location | None
    entries: list[LedgerEntry]  # oldest first
    total: int
    closing_balance: Decimal


def _effect(row: MovementRow, location_id: int | None) -> Decimal:
    m = row.movement
    if location_id is None:
        # Whole-warehouse view: a transfer moves stock but does not change the total.
        if m.type == "TRANSFER":
            return ZERO
        return m.quantity if m.to_location_id is not None else -m.quantity
    change = ZERO
    if m.to_location_id == location_id:
        change += m.quantity
    if m.from_location_id == location_id:
        change -= m.quantity
    return change


def product_ledger(
    session: Session, product_id: int, location_id: int | None, limit: int, offset: int
) -> Ledger:
    """Running balance per movement, computed from the ledger itself (never from the cache)."""
    product = get_product(session, product_id).product
    location = get_location(session, location_id) if location_id is not None else None
    running = ZERO
    entries: list[LedgerEntry] = []
    for row in repo.movement_rows_for_product(session, product_id):
        touches = location_id is None or location_id in (
            row.movement.from_location_id,
            row.movement.to_location_id,
        )
        if not touches:
            continue
        change = _effect(row, location_id)
        running += change
        entries.append(LedgerEntry(row, change, running))
    return Ledger(
        product=product,
        location=location,
        entries=entries[offset : offset + limit],
        total=len(entries),
        closing_balance=running,
    )


# ---------- low stock (rule 7) ----------


@dataclass(frozen=True)
class LowStockItem:
    product: Product
    on_hand: Decimal
    shortfall: Decimal


def low_stock(session: Session) -> list[LowStockItem]:
    totals = repo.totals_by_product(session)
    items = []
    for product in repo.all_products(session):
        on_hand = totals.get(product.id, ZERO)
        if on_hand <= product.reorder_level:  # "at or below"
            items.append(LowStockItem(product, on_hand, product.reorder_level - on_hand))
    return sorted(items, key=lambda i: (-i.shortfall, i.product.sku))


# ---------- valuation ----------


@dataclass(frozen=True)
class ValuationLine:
    product: Product
    on_hand: Decimal
    value: Decimal


@dataclass(frozen=True)
class Valuation:
    lines: list[ValuationLine]
    total_value: Decimal
    as_of: datetime


def valuation(session: Session) -> Valuation:
    totals = repo.totals_by_product(session)
    lines = []
    for product in repo.all_products(session):
        on_hand = totals.get(product.id, ZERO)
        lines.append(ValuationLine(product, on_hand, movement_value(on_hand, product.avg_cost)))
    return Valuation(lines, sum((line.value for line in lines), ZERO), utc_now())


# ---------- stock overview grid ----------


@dataclass(frozen=True)
class OverviewRow:
    product: Product
    quantities: dict[int, Decimal]  # location_id -> qty (non-zero only)
    total: Decimal


def stock_overview(session: Session) -> tuple[list[Location], list[OverviewRow]]:
    locations = list(repo.all_locations(session))
    cached = repo.cached_balances(session)
    rows = []
    for product in repo.all_products(session):
        quantities = {
            loc.id: cached[(product.id, loc.id)]
            for loc in locations
            if cached.get((product.id, loc.id), ZERO) != ZERO
        }
        rows.append(OverviewRow(product, quantities, sum(quantities.values(), ZERO)))
    return locations, rows
