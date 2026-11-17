"""godown stock: part of each product's stock kept in the godown, shelf refill level, godown <-> shop transfers

Revision ID: b6e2d9f4a1c3
Revises: a3d8f1c6e2b9
Create Date: 2026-11-02

inventory.qty_on_hand stays the whole stock. godown_qty is the part of it in the godown, so the shop shelf has
qty_on_hand - godown_qty. Existing stock starts as all on the shop shelf (godown_qty = 0).
"""
from alembic import op
import sqlalchemy as sa


revision = "b6e2d9f4a1c3"
down_revision = "a3d8f1c6e2b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inventory", sa.Column("godown_qty", sa.Numeric(12, 3), nullable=False, server_default="0"))
    op.add_column("inventory", sa.Column("shelf_min_qty", sa.Numeric(12, 3), nullable=True))
    op.create_check_constraint(
        "ck_inventory_godown_within_stock", "inventory", "godown_qty >= 0 AND godown_qty <= qty_on_hand"
    )
    op.create_table(
        "stock_transfers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("qty > 0", name="ck_stock_transfers_qty_positive"),
    )
    op.create_index("ix_stock_transfers_store_product", "stock_transfers", ["store_id", "product_id"])


def downgrade():
    op.drop_index("ix_stock_transfers_store_product", table_name="stock_transfers")
    op.drop_table("stock_transfers")
    op.drop_constraint("ck_inventory_godown_within_stock", "inventory", type_="check")
    op.drop_column("inventory", "shelf_min_qty")
    op.drop_column("inventory", "godown_qty")
