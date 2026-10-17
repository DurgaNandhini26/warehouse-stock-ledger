"""ORM models. The schema itself is owned by Alembic migrations in backend/migrations."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.types import ScaledDecimal, UTCDateTime

QTY_SCALE = 3  # 0.001 kg / litre; whole numbers enforced for pcs in the domain layer
COST_SCALE = 4  # unit and average cost, Rs with 4 decimals (1/100 paisa)
VALUE_SCALE = 2  # money totals, Rs.paise


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("unit IN ('kg', 'pcs', 'litre')", name="ck_products_unit"),
        CheckConstraint("reorder_level >= 0", name="ck_products_reorder_level"),
        CheckConstraint("avg_cost >= 0", name="ck_products_avg_cost"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(10))
    reorder_level: Mapped[Decimal] = mapped_column(ScaledDecimal(QTY_SCALE), default=Decimal(0))
    # Cached weighted average cost; recomputable by replaying movements (see reconcile).
    avg_cost: Mapped[Decimal] = mapped_column(ScaledDecimal(COST_SCALE), default=Decimal(0))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())


class Movement(Base):
    """Append-only. UPDATE and DELETE are blocked by database triggers (see migration 0001)."""

    __tablename__ = "movements"
    __table_args__ = (
        CheckConstraint(
            "type IN ('IN', 'OUT', 'TRANSFER', 'ADJUSTMENT')", name="ck_movements_type"
        ),
        CheckConstraint(
            "(type = 'IN' AND from_location_id IS NULL AND to_location_id IS NOT NULL)"
            " OR (type = 'OUT' AND from_location_id IS NOT NULL AND to_location_id IS NULL)"
            " OR (type = 'TRANSFER' AND from_location_id IS NOT NULL"
            "     AND to_location_id IS NOT NULL AND from_location_id <> to_location_id)"
            " OR (type = 'ADJUSTMENT' AND"
            "     ((from_location_id IS NULL) <> (to_location_id IS NULL)))",
            name="ck_movements_locations",
        ),
        CheckConstraint("quantity > 0", name="ck_movements_quantity"),
        CheckConstraint(
            "type <> 'IN' OR unit_cost > 0 OR reverses_movement_id IS NOT NULL",
            name="ck_movements_in_cost",
        ),
        CheckConstraint("unit_cost IS NULL OR unit_cost >= 0", name="ck_movements_unit_cost"),
        CheckConstraint("value IS NULL OR value >= 0", name="ck_movements_value"),
        CheckConstraint("(type = 'TRANSFER') = (unit_cost IS NULL)", name="ck_movements_valued"),
        CheckConstraint(
            "type <> 'ADJUSTMENT' OR reason_code IS NOT NULL", name="ck_movements_adj_reason"
        ),
        Index("ix_movements_product_id_id", "product_id", "id"),
        Index("ix_movements_from_location_id", "from_location_id"),
        Index("ix_movements_to_location_id", "to_location_id"),
        Index("ix_movements_created_at", "created_at"),
        Index("ix_movements_reference", "reference"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(12))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    from_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    to_location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"))
    quantity: Mapped[Decimal] = mapped_column(ScaledDecimal(QTY_SCALE))
    # IN: the purchase cost entered by the user. OUT / ADJUSTMENT: the average cost at the
    # moment of posting, frozen so later average changes never rewrite history.
    unit_cost: Mapped[Decimal | None] = mapped_column(ScaledDecimal(COST_SCALE))
    value: Mapped[Decimal | None] = mapped_column(ScaledDecimal(VALUE_SCALE))
    reason_code: Mapped[str | None] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(String(500))
    reference: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    created_by: Mapped[str] = mapped_column(String(100))
    reverses_movement_id: Mapped[int | None] = mapped_column(
        ForeignKey("movements.id"), unique=True
    )


class StockBalance(Base):
    """Cache of SUM(movements) per (product, location). Rebuildable via the reconcile endpoint."""

    __tablename__ = "stock_balances"
    __table_args__ = (CheckConstraint("quantity >= 0", name="ck_stock_balances_non_negative"),)

    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(ScaledDecimal(QTY_SCALE))
