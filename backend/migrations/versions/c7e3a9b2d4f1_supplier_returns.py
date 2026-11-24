"""supplier returns: stocked goods sent back to the supplier, with a debit note for their value

Revision ID: c7e3a9b2d4f1
Revises: b6e2d9f4a1c3
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa


revision = "c7e3a9b2d4f1"
down_revision = "b6e2d9f4a1c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_returns",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("return_number", sa.String(40), nullable=False, unique=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("stock_batches.id"), nullable=False),
        sa.Column("goods_receipt_id", sa.Integer(), sa.ForeignKey("goods_receipts.id"), nullable=False),
        sa.Column("qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("debit_note_id", sa.Integer(), sa.ForeignKey("supplier_payments.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("qty > 0", name="ck_supplier_returns_qty_positive"),
    )
    op.create_index("ix_supplier_returns_supplier_id", "supplier_returns", ["supplier_id"])


def downgrade():
    op.drop_index("ix_supplier_returns_supplier_id", table_name="supplier_returns")
    op.drop_table("supplier_returns")
