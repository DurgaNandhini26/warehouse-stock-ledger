import csv
import io
from decimal import Decimal

from fastapi import APIRouter
from fastapi.responses import Response

from app.api import schemas
from app.api.deps import IdPath, Limit, Offset, OptionalId, SessionDep
from app.api.presenters import location_out, movement_out, product_out
from app.db import repositories as repo
from app.services import reports
from app.services.catalog import get_location, get_product
from app.services.reconciliation import ReconciliationReport, reconcile

router = APIRouter()


@router.get("/balances", response_model=schemas.BalancesOut, tags=["balances"])
def list_balances(
    session: SessionDep,
    product_id: OptionalId = None,
    location_id: OptionalId = None,
    include_zero: bool = False,
):
    """Balances by product, by location, or both. Filtering by product also returns its total."""
    if product_id is not None:
        get_product(session, product_id)  # 404 for unknown ids instead of an empty list
    if location_id is not None:
        get_location(session, location_id)
    rows = repo.balance_rows(session, product_id, location_id, include_zero)
    total = sum((r.quantity for r in rows), Decimal(0)) if product_id is not None else None
    return schemas.BalancesOut(
        items=[schemas.BalanceOut(**r.__dict__) for r in rows], total_quantity=total
    )


@router.get("/products/{product_id}/ledger", response_model=schemas.LedgerOut, tags=["products"])
def product_ledger(
    product_id: IdPath,
    session: SessionDep,
    location_id: OptionalId = None,
    limit: Limit = 200,
    offset: Offset = 0,
):
    """Every movement of the product, oldest first, with the running balance after each one.
    Pass location_id to follow a single bin instead of the warehouse total."""
    ledger = reports.product_ledger(session, product_id, location_id, limit, offset)
    on_hand = repo.total_on_hand(session, product_id)
    return schemas.LedgerOut(
        product=product_out(ledger.product, on_hand),
        location=location_out(ledger.location) if ledger.location else None,
        entries=[
            schemas.LedgerEntryOut(
                movement=movement_out(e.row),
                quantity_change=e.quantity_change,
                balance_after=e.balance_after,
            )
            for e in ledger.entries
        ],
        total=ledger.total,
        limit=limit,
        offset=offset,
        closing_balance=ledger.closing_balance,
    )


@router.get("/products/{product_id}/ledger.csv", tags=["products"])
def product_ledger_csv(product_id: IdPath, session: SessionDep, location_id: OptionalId = None):
    """Stretch: the full ledger as CSV (timestamps in UTC, ISO 8601)."""
    ledger = reports.product_ledger(session, product_id, location_id, limit=10**9, offset=0)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "movement_id", "created_at_utc", "type", "from", "to", "quantity", "change",
            "balance_after", "unit_cost", "value", "reason_code", "reason", "reference",
            "created_by", "reverses_movement_id", "reversed_by_movement_id",
        ]
    )  # fmt: skip
    for e in ledger.entries:
        m = e.row.movement
        writer.writerow(
            [
                m.id, m.created_at.isoformat(), m.type, e.row.from_location_code or "",
                e.row.to_location_code or "", m.quantity, e.quantity_change, e.balance_after,
                m.unit_cost if m.unit_cost is not None else "",
                m.value if m.value is not None else "", m.reason_code or "",
                _csv_safe(m.reason), _csv_safe(m.reference), _csv_safe(m.created_by),
                m.reverses_movement_id or "", e.row.reversed_by_movement_id or "",
            ]
        )  # fmt: skip
    filename = f"ledger-{ledger.product.sku}.csv"
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_safe(value: str | None) -> str:
    """Neutralise spreadsheet formula injection in user-entered text."""
    if not value:
        return ""
    return "'" + value if value[0] in "=+-@\t\r" else value


@router.get("/reports/low-stock", response_model=list[schemas.LowStockOut], tags=["reports"])
def low_stock(session: SessionDep):
    """Products whose total balance across all locations is at or below the reorder level."""
    return [
        schemas.LowStockOut(product=product_out(i.product, i.on_hand), shortfall=i.shortfall)
        for i in reports.low_stock(session)
    ]


@router.get("/reports/valuation", response_model=schemas.ValuationOut, tags=["reports"])
def valuation(session: SessionDep):
    """Quantity x weighted average cost per product, plus the warehouse total."""
    result = reports.valuation(session)
    return schemas.ValuationOut(
        lines=[
            schemas.ValuationLineOut(
                product_id=line.product.id,
                sku=line.product.sku,
                name=line.product.name,
                unit=line.product.unit,
                on_hand=line.on_hand,
                avg_cost=line.product.avg_cost,
                value=line.value,
            )
            for line in result.lines
        ],
        total_value=result.total_value,
        as_of=result.as_of,
    )


@router.get("/reports/stock-overview", response_model=schemas.OverviewOut, tags=["reports"])
def stock_overview(session: SessionDep):
    """Products x locations grid of current balances."""
    locations, rows = reports.stock_overview(session)
    return schemas.OverviewOut(
        locations=[location_out(loc) for loc in locations],
        rows=[
            schemas.OverviewRowOut(
                product_id=r.product.id,
                sku=r.product.sku,
                name=r.product.name,
                unit=r.product.unit,
                reorder_level=r.product.reorder_level,
                is_low_stock=r.total <= r.product.reorder_level,
                quantities=r.quantities,
                total=r.total,
            )
            for r in rows
        ],
    )


def _reconciliation_out(report: ReconciliationReport) -> schemas.ReconciliationOut:
    return schemas.ReconciliationOut(
        consistent=report.consistent,
        repaired=report.repaired,
        checked_at=report.checked_at,
        balances_checked=report.balances_checked,
        products_checked=report.products_checked,
        balance_drift=[
            schemas.BalanceDriftOut(
                product_id=d.product_id,
                sku=d.sku,
                location_id=d.location_id,
                location_code=d.location_code,
                cached=d.cached,
                expected=d.expected,
                difference=d.difference,
            )
            for d in report.balance_drift
        ],
        average_cost_drift=[
            schemas.AverageCostDriftOut(**d.__dict__) for d in report.average_cost_drift
        ],
    )


@router.get("/reconciliation", response_model=schemas.ReconciliationOut, tags=["reconciliation"])
def check_reconciliation(session: SessionDep):
    """Recompute every balance and average cost from the movements; report drift. Read-only."""
    return _reconciliation_out(reconcile(session, repair=False))


@router.post("/reconciliation", response_model=schemas.ReconciliationOut, tags=["reconciliation"])
def repair_reconciliation(session: SessionDep):
    """Same check, then overwrite the cache with the recomputed values. Returns what was fixed."""
    return _reconciliation_out(reconcile(session, repair=True))
