"""Sample data for a small agri-inputs distributor. All names and references are invented."""

from datetime import UTC, datetime, timedelta
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


# (days ago, type, sku, from bin, to bin, quantity, unit cost / adjustment reason, reference, by)
# Quantities are in the product's unit (kg / litre / pcs).
MOVEMENTS = [
    (14, "IN", "RICE-SNM-25", None, "DOCK", "2000", "52.50", "INV-SRA-1041", "Kavya Rao"),
    (14, "TRANSFER", "RICE-SNM-25", "DOCK", "A-01", "1500", None, None, "Arun Pillai"),
    (14, "TRANSFER", "RICE-SNM-25", "DOCK", "A-02", "500", None, None, "Arun Pillai"),
    (13, "IN", "ATTA-WHT-10", None, "A-01", "800", "38.20", "INV-GMF-2207", "Kavya Rao"),
    (13, "IN", "OIL-SUN-1L", None, "B-01", "600", "142.00", "INV-SUN-0093", "Kavya Rao"),
    (12, "IN", "OIL-GNUT-15", None, "B-01", "300", "265.75", "INV-KPO-0410", "Kavya Rao"),
    (12, "IN", "DAL-TUR-1", None, "A-02", "400", "128.40", "INV-DLS-7781", "Kavya Rao"),
    (11, "IN", "SUGAR-50", None, "DOCK", "1000", "41.10", "INV-SGR-3302", "Kavya Rao"),
    (11, "TRANSFER", "SUGAR-50", "DOCK", "A-01", "1000", None, None, "Arun Pillai"),
    (11, "IN", "JUTE-BAG-L", None, "C-01", "500", "18.00", "INV-JBC-0021", "Kavya Rao"),
    (10, "IN", "TEA-DUST-250", None, "C-01", "240", "62.50", "INV-ATC-5590", "Kavya Rao"),
    (9, "OUT", "RICE-SNM-25", "A-01", None, "650", None, "SO-24-1187", "Meera Nair"),
    (9, "OUT", "OIL-SUN-1L", "B-01", None, "180", None, "SO-24-1188", "Meera Nair"),
    (8, "IN", "RICE-SNM-25", None, "A-01", "1000", "55.00", "INV-SRA-1066", "Kavya Rao"),
    (8, "OUT", "ATTA-WHT-10", "A-01", None, "420", None, "SO-24-1190", "Meera Nair"),
    (7, "ADJUSTMENT", "SUGAR-50", "A-01", None, "-50", "damaged", None, "Ravi Shetty"),
    (7, "OUT", "DAL-TUR-1", "A-02", None, "290", None, "SO-24-1194", "Meera Nair"),
    (6, "IN", "OIL-SUN-1L", None, "B-01", "300", "146.50", "INV-SUN-0101", "Kavya Rao"),
    (6, "OUT", "OIL-GNUT-15", "B-01", None, "255", None, "SO-24-1198", "Meera Nair"),
    (5, "OUT", "SUGAR-50", "A-01", None, "700", None, "SO-24-1201", "Meera Nair"),
    (5, "TRANSFER", "OIL-SUN-1L", "B-01", "QC-HOLD", "12", None, None, "Ravi Shetty"),
    (4, "ADJUSTMENT", "OIL-SUN-1L", "QC-HOLD", None, "-12", "expired", None, "Ravi Shetty"),
    (4, "OUT", "JUTE-BAG-L", "C-01", None, "430", None, "SO-24-1205", "Meera Nair"),
    (3, "OUT", "TEA-DUST-250", "C-01", None, "60", None, "SO-24-1209", "Meera Nair"),
    (3, "ADJUSTMENT", "TEA-DUST-250", "C-01", None, "-2", "count_correction", None, "Ravi Shetty"),
    (2, "OUT", "RICE-SNM-25", "A-02", None, "300", None, "SO-24-1212", "Meera Nair"),
    (1, "OUT", "ATTA-WHT-10", "A-01", None, "150", None, "SO-24-1216", "Meera Nair"),
]
# A mistaken shipment (keyed against the wrong order) that is then reversed.
MISTAKE = (1, "OUT", "DAL-TUR-1", "A-02", None, "40", None, "SO-24-1217", "Meera Nair")


def _post(session: Session, row: tuple, products: dict, bins: dict, today: datetime):
    from app.domain.enums import AdjustmentReason, MovementType
    from app.domain.movements import MovementRequest, adjustment_request
    from app.services.movements import post_movement

    days, type_, sku, src, dst, qty, extra, ref, by = row
    when = today - timedelta(days=days)
    if type_ == "ADJUSTMENT":
        loc = bins[src or dst]
        request = adjustment_request(loc, Decimal(qty), AdjustmentReason(extra), None)
    else:
        request = MovementRequest(
            type=MovementType(type_),
            quantity=Decimal(qty),
            from_location_id=bins[src] if src else None,
            to_location_id=bins[dst] if dst else None,
            unit_cost=Decimal(extra) if type_ == "IN" else None,
        )
    return post_movement(session, products[sku], request, created_by=by, reference=ref, now=when)


def seed_if_empty(database_url: str) -> bool:
    from app.services.movements import reverse_movement

    engine = build_engine(database_url)
    try:
        with build_session_factory(engine)() as session:
            with transaction(session):
                if session.scalar(select(func.count()).select_from(Product)):
                    return False
                today = datetime.now(UTC).replace(hour=5, minute=30, second=0, microsecond=0)
                _seed_catalog(session, today - timedelta(days=15))
            products = {p.sku: p.id for p in session.scalars(select(Product))}
            bins = {loc.code: loc.id for loc in session.scalars(select(Location))}
            for row in MOVEMENTS:
                _post(session, row, products, bins, today)
            mistake = _post(session, MISTAKE, products, bins, today)
            reverse_movement(
                session,
                mistake.id,
                reason="Keyed against wrong sales order; goods never left A-02",
                created_by="Ravi Shetty",
                now=today - timedelta(hours=20),
            )
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
