"""MRP + HSN on products and bill lines; sale returns (credit notes)

Also joins the two migration ends 0f5ec6faaded and c4d7e2a9f1b3.

Revision ID: d5e8f3b1a2c4
Revises: 0f5ec6faaded, c4d7e2a9f1b3
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d5e8f3b1a2c4"
down_revision = ("0f5ec6faaded", "c4d7e2a9f1b3")
branch_labels = None
depends_on = None

# Already exists (payments table); reuse it, don't CREATE TYPE again.
payment_method = postgresql.ENUM("CASH", "CARD", "UPI", "SPLIT", name="payment_method", create_type=False)


def upgrade():
    # MRP (incl. GST) and HSN code: on the product, and snapshotted on each bill line.
    op.add_column("products", sa.Column("mrp", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("products", sa.Column("hsn_code", sa.String(length=8), nullable=True))
    op.add_column("sale_items", sa.Column("mrp", sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column("sale_items", sa.Column("hsn_code", sa.String(length=8), nullable=True))

    op.create_table(
        "sale_returns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_number", sa.String(length=40), nullable=True),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        sa.Column("shift_id", sa.Integer(), nullable=False),
        sa.Column("cashier_id", sa.Integer(), nullable=False),
        sa.Column("approved_by_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("refund_method", payment_method, nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("refund_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("refund_amount >= 0", name=op.f("ck_sale_returns_refund_not_negative")),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"], name=op.f("fk_sale_returns_sale_id_sales")),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], name=op.f("fk_sale_returns_store_id_stores")),
        sa.ForeignKeyConstraint(
            ["shift_id"], ["cashier_shifts.id"], name=op.f("fk_sale_returns_shift_id_cashier_shifts")
        ),
        sa.ForeignKeyConstraint(["cashier_id"], ["users.id"], name=op.f("fk_sale_returns_cashier_id_users")),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], name=op.f("fk_sale_returns_approved_by_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_returns")),
        sa.UniqueConstraint("return_number", name=op.f("uq_sale_returns_return_number")),
    )
    with op.batch_alter_table("sale_returns", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sale_returns_sale_id"), ["sale_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sale_returns_shift_id"), ["shift_id"], unique=False)

    op.create_table(
        "sale_return_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("return_id", sa.Integer(), nullable=False),
        sa.Column("sale_item_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=False),
        sa.Column("hsn_code", sa.String(length=8), nullable=True),
        sa.Column("tax_rate", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("qty", sa.Numeric(precision=12, scale=3), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("refund_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("restocked", sa.Boolean(), nullable=False),
        sa.CheckConstraint("qty > 0", name=op.f("ck_sale_return_items_qty_positive")),
        sa.ForeignKeyConstraint(
            ["return_id"], ["sale_returns.id"], name=op.f("fk_sale_return_items_return_id_sale_returns"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["sale_item_id"], ["sale_items.id"], name=op.f("fk_sale_return_items_sale_item_id_sale_items")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_sale_return_items_product_id_products")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sale_return_items")),
    )
    with op.batch_alter_table("sale_return_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_sale_return_items_return_id"), ["return_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_sale_return_items_sale_item_id"), ["sale_item_id"], unique=False)


def downgrade():
    with op.batch_alter_table("sale_return_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sale_return_items_sale_item_id"))
        batch_op.drop_index(batch_op.f("ix_sale_return_items_return_id"))
    op.drop_table("sale_return_items")
    with op.batch_alter_table("sale_returns", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sale_returns_shift_id"))
        batch_op.drop_index(batch_op.f("ix_sale_returns_sale_id"))
    op.drop_table("sale_returns")
    # payment_method is still used by payments: never drop it here.

    op.drop_column("sale_items", "hsn_code")
    op.drop_column("sale_items", "mrp")
    op.drop_column("products", "hsn_code")
    op.drop_column("products", "mrp")
