"""Sample data for a small agri-inputs distributor. All names and references are invented."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import Location, Product, StockBalance
from app.db.session import build_engine, build_session_factory, transaction

PRODUCTS = [
    # sku, name, unit, reorder level
    ("RICE-SNM-25", "Sona Masoori rice, 25 kg bag", "kg", "500"),
    ("ATTA-WHT-10", "Whole wheat atta, 10 kg bag", "kg", "200"),
    ("OIL-SUN-1L", "Refined sunflower oil, 1 L pouch", "litre", "120"),
    ("OIL-GNUT-15", "Cold-pressed groundnut oil, 15 L tin", "litre", "60"),
    ("DAL-TUR-1", "Toor dal, 1 kg pack", "kg", "150"),
    ("SUGAR-50", "Sugar, 50 kg sack", "kg", "300"),
    ("JUTE-BAG-L", "Jute carry bag, large", "pcs", "100"),
    ("TEA-DUST-250", "Assam tea dust, 250 g pack", "pcs", "80"),
]

LOCATIONS = [
    ("A-01", "Aisle A, rack 1 - dry grains (ground level)"),
    ("A-02", "Aisle A, rack 2 - dry grains (upper)"),
    ("B-01", "Aisle B, rack 1 - edible oils"),
    ("C-01", "Aisle C - packaging and sundries"),
    ("DOCK", "Receiving dock staging area"),
    ("QC-HOLD", "Quality hold - damaged / under inspection"),
]


def _seed_catalog(session: Session, now: datetime) -> None:
    for sku, name, unit, reorder in PRODUCTS:
        session.add(
            Product(sku=sku, name=name, unit=unit, reorder_level=Decimal(reorder), created_at=now)
        )
    for code, description in LOCATIONS:
        session.add(Location(code=code, description=description, created_at=now))


def seed_if_empty(database_url: str) -> bool:
    engine = build_engine(database_url)
    try:
        with build_session_factory(engine)() as session, transaction(session):
            if session.scalar(select(func.count()).select_from(Product)):
                return False
            _seed_catalog(session, datetime.now(UTC))
        return True
    finally:
        engine.dispose()


def corrupt_cached_balance(
    database_url: str, sku: str, location_code: str, quantity: Decimal
) -> None:
    """Overwrite one cached balance without a movement, so reconcile has drift to find."""
    engine = build_engine(database_url)
    try:
        with build_session_factory(engine)() as session, transaction(session):
            product = session.scalar(select(Product).where(Product.sku == sku.upper()))
            location = session.scalar(
                select(Location).where(Location.code == location_code.upper())
            )
            if product is None or location is None:
                raise SystemExit("unknown SKU or bin code")
            existing = session.get(StockBalance, (product.id, location.id))
            if existing is None:
                session.add(
                    StockBalance(product_id=product.id, location_id=location.id, quantity=quantity)
                )
            else:
                session.execute(
                    update(StockBalance)
                    .where(
                        StockBalance.product_id == product.id,
                        StockBalance.location_id == location.id,
                    )
                    .values(quantity=quantity)
                )
    finally:
        engine.dispose()
