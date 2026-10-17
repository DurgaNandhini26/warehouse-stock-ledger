"""All SQL lives here. Functions take a Session and never commit; services own transactions."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.orm import Session, aliased

from app.db.models import Location, Movement, Product, StockBalance

# ---------- products & locations ----------


def get_product(session: Session, product_id: int) -> Product | None:
    return session.get(Product, product_id)


def lock_product(session: Session, product_id: int) -> Product | None:
    """SELECT ... FOR UPDATE (no-op on SQLite, which is already write-locked by BEGIN IMMEDIATE).

    populate_existing makes sure we see the row as it is *after* acquiring the lock, not a
    stale copy from the session's identity map.
    """
    stmt = (
        select(Product)
        .where(Product.id == product_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return session.scalar(stmt)


def lock_all_products(session: Session) -> Sequence[Product]:
    """Lock every product row, in id order so two lockers can never deadlock."""
    stmt = (
        select(Product)
        .order_by(Product.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return session.scalars(stmt).all()


def get_product_by_sku(session: Session, sku: str) -> Product | None:
    return session.scalar(select(Product).where(Product.sku == sku))


def list_products(
    session: Session, search: str | None, limit: int, offset: int
) -> tuple[Sequence[Product], int]:
    stmt = select(Product)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Product.sku).like(pattern), func.lower(Product.name).like(pattern))
        )
    return _page(session, stmt.order_by(Product.sku), limit, offset)


def all_products(session: Session) -> Sequence[Product]:
    return session.scalars(select(Product).order_by(Product.sku)).all()


def get_location(session: Session, location_id: int) -> Location | None:
    return session.get(Location, location_id)


def get_location_by_code(session: Session, code: str) -> Location | None:
    return session.scalar(select(Location).where(Location.code == code))


def list_locations(session: Session, limit: int, offset: int) -> tuple[Sequence[Location], int]:
    return _page(session, select(Location).order_by(Location.code), limit, offset)


def all_locations(session: Session) -> Sequence[Location]:
    return session.scalars(select(Location).order_by(Location.code)).all()


def existing_location_ids(session: Session, ids: Iterable[int]) -> set[int]:
    wanted = set(ids)
    if not wanted:
        return set()
    return set(session.scalars(select(Location.id).where(Location.id.in_(wanted))).all())


# ---------- balances (cache) ----------


def balances_for(session: Session, product_id: int, location_ids: Iterable[int]) -> dict:
    ids = list(location_ids)
    if not ids:
        return {}
    rows = session.execute(
        select(StockBalance.location_id, StockBalance.quantity).where(
            StockBalance.product_id == product_id, StockBalance.location_id.in_(ids)
        )
    ).all()
    return {loc: qty for loc, qty in rows}


def total_on_hand(session: Session, product_id: int) -> Decimal:
    total = session.scalar(
        select(func.sum(StockBalance.quantity)).where(StockBalance.product_id == product_id)
    )
    return total if total is not None else Decimal(0)


def totals_by_product(session: Session) -> dict[int, Decimal]:
    rows = session.execute(
        select(StockBalance.product_id, func.sum(StockBalance.quantity)).group_by(
            StockBalance.product_id
        )
    ).all()
    return {pid: qty for pid, qty in rows}


def apply_balance_delta(
    session: Session, product_id: int, location_id: int, delta: Decimal
) -> None:
    """Atomic `quantity = quantity + delta` in SQL; inserts the row on first receipt.

    The CHECK (quantity >= 0) constraint is a last line of defence behind the domain check.
    """
    result = session.execute(
        update(StockBalance)
        .where(StockBalance.product_id == product_id, StockBalance.location_id == location_id)
        .values(quantity=StockBalance.quantity + delta)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        session.add(StockBalance(product_id=product_id, location_id=location_id, quantity=delta))
        session.flush()


def set_cached_balance(
    session: Session, product_id: int, location_id: int, quantity: Decimal
) -> None:
    result = session.execute(
        update(StockBalance)
        .where(StockBalance.product_id == product_id, StockBalance.location_id == location_id)
        .values(quantity=quantity)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        session.add(StockBalance(product_id=product_id, location_id=location_id, quantity=quantity))
        session.flush()


def cached_balances(session: Session) -> dict[tuple[int, int], Decimal]:
    rows = session.execute(
        select(StockBalance.product_id, StockBalance.location_id, StockBalance.quantity)
    ).all()
    return {(p, loc): q for p, loc, q in rows}


def expected_balances_from_movements(session: Session) -> dict[tuple[int, int], Decimal]:
    """Recompute every (product, location) balance from the ledger alone."""
    inbound = session.execute(
        select(Movement.product_id, Movement.to_location_id, func.sum(Movement.quantity))
        .where(Movement.to_location_id.is_not(None))
        .group_by(Movement.product_id, Movement.to_location_id)
    ).all()
    outbound = session.execute(
        select(Movement.product_id, Movement.from_location_id, func.sum(Movement.quantity))
        .where(Movement.from_location_id.is_not(None))
        .group_by(Movement.product_id, Movement.from_location_id)
    ).all()
    expected: dict[tuple[int, int], Decimal] = {}
    for pid, loc, qty in inbound:
        expected[(pid, loc)] = expected.get((pid, loc), Decimal(0)) + qty
    for pid, loc, qty in outbound:
        expected[(pid, loc)] = expected.get((pid, loc), Decimal(0)) - qty
    return expected


@dataclass(frozen=True)
class BalanceRow:
    product_id: int
    sku: str
    product_name: str
    unit: str
    location_id: int
    location_code: str
    quantity: Decimal


def balance_rows(
    session: Session, product_id: int | None, location_id: int | None, include_zero: bool
) -> list[BalanceRow]:
    stmt = (
        select(
            StockBalance.product_id,
            Product.sku,
            Product.name,
            Product.unit,
            StockBalance.location_id,
            Location.code,
            StockBalance.quantity,
        )
        .join(Product, Product.id == StockBalance.product_id)
        .join(Location, Location.id == StockBalance.location_id)
        .order_by(Product.sku, Location.code)
    )
    if product_id is not None:
        stmt = stmt.where(StockBalance.product_id == product_id)
    if location_id is not None:
        stmt = stmt.where(StockBalance.location_id == location_id)
    if not include_zero:
        stmt = stmt.where(StockBalance.quantity != Decimal(0))
    return [BalanceRow(*row) for row in session.execute(stmt).all()]


# ---------- movements (append-only) ----------


def insert_movement(session: Session, **fields) -> Movement:
    movement = Movement(**fields)
    session.add(movement)
    session.flush()  # assigns the id inside the transaction
    return movement


def get_movement(session: Session, movement_id: int) -> Movement | None:
    return session.get(Movement, movement_id)


def reversal_of(session: Session, movement_id: int) -> int | None:
    """Id of the movement that reversed `movement_id`, if any."""
    return session.scalar(select(Movement.id).where(Movement.reverses_movement_id == movement_id))


@dataclass(frozen=True)
class MovementFilters:
    product_id: int | None = None
    location_id: int | None = None
    type: str | None = None
    reference: str | None = None
    created_from: datetime | None = None
    created_before: datetime | None = None


@dataclass(frozen=True)
class MovementRow:
    """A movement joined with the codes a reader needs and whether it was reversed."""

    movement: Movement
    sku: str
    from_location_code: str | None
    to_location_code: str | None
    reversed_by_movement_id: int | None


def _movement_rows_query() -> Select:
    src = aliased(Location)
    dst = aliased(Location)
    reversal = aliased(Movement)
    return (
        select(Movement, Product.sku, src.code, dst.code, reversal.id)
        .join(Product, Product.id == Movement.product_id)
        .outerjoin(src, src.id == Movement.from_location_id)
        .outerjoin(dst, dst.id == Movement.to_location_id)
        .outerjoin(reversal, reversal.reverses_movement_id == Movement.id)
    )


def list_movements(
    session: Session, filters: MovementFilters, limit: int, offset: int
) -> tuple[list[MovementRow], int]:
    stmt = _movement_rows_query()
    if filters.product_id is not None:
        stmt = stmt.where(Movement.product_id == filters.product_id)
    if filters.location_id is not None:
        stmt = stmt.where(
            or_(
                Movement.from_location_id == filters.location_id,
                Movement.to_location_id == filters.location_id,
            )
        )
    if filters.type is not None:
        stmt = stmt.where(Movement.type == filters.type)
    if filters.reference:
        stmt = stmt.where(func.lower(Movement.reference).like(f"%{filters.reference.lower()}%"))
    if filters.created_from is not None:
        stmt = stmt.where(Movement.created_at >= filters.created_from)
    if filters.created_before is not None:
        stmt = stmt.where(Movement.created_at < filters.created_before)
    rows, total = _page(session, stmt.order_by(Movement.id.desc()), limit, offset, scalars=False)
    return [MovementRow(*row) for row in rows], total


def get_movement_row(session: Session, movement_id: int) -> MovementRow | None:
    row = session.execute(_movement_rows_query().where(Movement.id == movement_id)).first()
    return MovementRow(*row) if row else None


def movement_rows_for_product(session: Session, product_id: int) -> list[MovementRow]:
    stmt = _movement_rows_query().where(Movement.product_id == product_id).order_by(Movement.id)
    return [MovementRow(*row) for row in session.execute(stmt).all()]


def all_movements_in_order(session: Session) -> Sequence[Movement]:
    return session.scalars(select(Movement).order_by(Movement.id)).all()


# ---------- helpers ----------


def _page(session: Session, stmt: Select, limit: int, offset: int, *, scalars: bool = True):
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    paged = stmt.limit(limit).offset(offset)
    items = session.scalars(paged).all() if scalars else session.execute(paged).all()
    return items, total or 0
