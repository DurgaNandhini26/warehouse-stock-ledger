"""Initial schema: products, locations, append-only movements, balance cache.

Decimals are stored as scaled BIGINTs (see app/db/types.py):
  quantity / reorder_level: x1000, unit_cost / avg_cost: x10^8, value: x100.

Revision ID: 0001
Revises:
Create Date: 2026-10-17
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sku", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("unit", sa.String(10), nullable=False),
        sa.Column("reorder_level", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("avg_cost", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("unit IN ('kg', 'pcs', 'litre')", name="ck_products_unit"),
        sa.CheckConstraint("reorder_level >= 0", name="ck_products_reorder_level"),
        sa.CheckConstraint("avg_cost >= 0", name="ck_products_avg_cost"),
    )

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("description", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "movements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("type", sa.String(12), nullable=False),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("from_location_id", sa.Integer, sa.ForeignKey("locations.id")),
        sa.Column("to_location_id", sa.Integer, sa.ForeignKey("locations.id")),
        sa.Column("quantity", sa.BigInteger, nullable=False),
        sa.Column("unit_cost", sa.BigInteger),
        sa.Column("value", sa.BigInteger),
        sa.Column("reason_code", sa.String(30)),
        sa.Column("reason", sa.String(500)),
        sa.Column("reference", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column(
            "reverses_movement_id",
            sa.Integer,
            sa.ForeignKey("movements.id"),
            unique=True,  # a movement can be reversed at most once, even under races
        ),
        sa.CheckConstraint(
            "type IN ('IN', 'OUT', 'TRANSFER', 'ADJUSTMENT')", name="ck_movements_type"
        ),
        sa.CheckConstraint(
            "(type = 'IN' AND from_location_id IS NULL AND to_location_id IS NOT NULL)"
            " OR (type = 'OUT' AND from_location_id IS NOT NULL AND to_location_id IS NULL)"
            " OR (type = 'TRANSFER' AND from_location_id IS NOT NULL"
            "     AND to_location_id IS NOT NULL AND from_location_id <> to_location_id)"
            " OR (type = 'ADJUSTMENT' AND"
            "     ((from_location_id IS NULL) <> (to_location_id IS NULL)))",
            name="ck_movements_locations",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_movements_quantity"),
        sa.CheckConstraint(
            "type <> 'IN' OR unit_cost > 0 OR reverses_movement_id IS NOT NULL",
            name="ck_movements_in_cost",
        ),
        sa.CheckConstraint("unit_cost IS NULL OR unit_cost >= 0", name="ck_movements_unit_cost"),
        sa.CheckConstraint("value IS NULL OR value >= 0", name="ck_movements_value"),
        sa.CheckConstraint("(type = 'TRANSFER') = (unit_cost IS NULL)", name="ck_movements_valued"),
        sa.CheckConstraint(
            "type <> 'ADJUSTMENT' OR reason_code IS NOT NULL", name="ck_movements_adj_reason"
        ),
    )
    op.create_index("ix_movements_product_id_id", "movements", ["product_id", "id"])
    op.create_index("ix_movements_from_location_id", "movements", ["from_location_id"])
    op.create_index("ix_movements_to_location_id", "movements", ["to_location_id"])
    op.create_index("ix_movements_created_at", "movements", ["created_at"])
    op.create_index("ix_movements_reference", "movements", ["reference"])

    op.create_table(
        "stock_balances",
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), primary_key=True),
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id"), primary_key=True),
        sa.Column("quantity", sa.BigInteger, nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_stock_balances_non_negative"),
    )

    # Rule 1 at the storage level: even a buggy code path or a manual SQL session cannot
    # edit or delete ledger rows.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION forbid_movement_change() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'movements are immutable; post a reversal instead';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER movements_immutable BEFORE UPDATE OR DELETE ON movements"
            " FOR EACH ROW EXECUTE FUNCTION forbid_movement_change()"
        )
    else:
        op.execute(
            "CREATE TRIGGER movements_no_update BEFORE UPDATE ON movements BEGIN"
            " SELECT RAISE(ABORT, 'movements are immutable; post a reversal instead'); END"
        )
        op.execute(
            "CREATE TRIGGER movements_no_delete BEFORE DELETE ON movements BEGIN"
            " SELECT RAISE(ABORT, 'movements are immutable; post a reversal instead'); END"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS movements_immutable ON movements")
        op.execute("DROP FUNCTION IF EXISTS forbid_movement_change()")
    else:
        op.execute("DROP TRIGGER IF EXISTS movements_no_update")
        op.execute("DROP TRIGGER IF EXISTS movements_no_delete")
    op.drop_table("stock_balances")
    op.drop_table("movements")
    op.drop_table("locations")
    op.drop_table("products")
