"""offer improvements: % cap, buy-x-get-y, quantity price, applied-offer tracking, manual discounts

Revision ID: a7c3e1d9b2f4
Revises: f1a2b3c4d5e6
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa


revision = "a7c3e1d9b2f4"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    # New offer types. Postgres needs ALTER TYPE ... ADD VALUE to run outside a transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE discount_type ADD VALUE IF NOT EXISTS 'BUY_X_GET_Y'")
        op.execute("ALTER TYPE discount_type ADD VALUE IF NOT EXISTS 'QTY_PRICE'")

    # discounts: cap for % offers, quantities for the new types.
    op.add_column("discounts", sa.Column("max_discount_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("discounts", sa.Column("buy_qty", sa.Integer(), nullable=True))
    op.add_column("discounts", sa.Column("get_qty", sa.Integer(), nullable=True))
    # "Buy X get Y" has no rupee/percent value, so value may now be 0.
    op.drop_constraint(op.f("ck_discounts_value_positive"), "discounts", type_="check")
    op.create_check_constraint(op.f("ck_discounts_value_not_negative"), "discounts", "value >= 0")

    # sale_items: which item offer was applied, plus the manual (counter) discount.
    op.add_column("sale_items", sa.Column("offer_id", sa.Integer(), nullable=True))
    op.add_column("sale_items", sa.Column("offer_name", sa.String(100), nullable=True))
    op.add_column("sale_items", sa.Column("offer_discount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("sale_items", sa.Column("manual_discount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("sale_items", sa.Column("manual_discount_reason", sa.String(100), nullable=True))
    op.add_column("sale_items", sa.Column("manual_discount_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(op.f("fk_sale_items_offer_id_discounts"), "sale_items", "discounts", ["offer_id"], ["id"])
    op.create_foreign_key(
        op.f("fk_sale_items_manual_discount_by_id_users"), "sale_items", "users", ["manual_discount_by_id"], ["id"]
    )

    # sales: which bill offer was applied.
    op.add_column("sales", sa.Column("bill_offer_id", sa.Integer(), nullable=True))
    op.add_column("sales", sa.Column("bill_offer_name", sa.String(100), nullable=True))
    op.add_column("sales", sa.Column("bill_offer_discount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.create_foreign_key(op.f("fk_sales_bill_offer_id_discounts"), "sales", "discounts", ["bill_offer_id"], ["id"])


def downgrade():
    op.drop_constraint(op.f("fk_sales_bill_offer_id_discounts"), "sales", type_="foreignkey")
    for col in ("bill_offer_discount", "bill_offer_name", "bill_offer_id"):
        op.drop_column("sales", col)

    op.drop_constraint(op.f("fk_sale_items_manual_discount_by_id_users"), "sale_items", type_="foreignkey")
    op.drop_constraint(op.f("fk_sale_items_offer_id_discounts"), "sale_items", type_="foreignkey")
    for col in ("manual_discount_by_id", "manual_discount_reason", "manual_discount", "offer_discount", "offer_name", "offer_id"):
        op.drop_column("sale_items", col)

    # Offers of the new types can't exist under the old rules.
    op.execute("DELETE FROM discounts WHERE discount_type IN ('BUY_X_GET_Y', 'QTY_PRICE')")
    op.drop_constraint(op.f("ck_discounts_value_not_negative"), "discounts", type_="check")
    op.create_check_constraint(op.f("ck_discounts_value_positive"), "discounts", "value > 0")
    for col in ("get_qty", "buy_qty", "max_discount_amount"):
        op.drop_column("discounts", col)
    # Postgres can't remove enum values; BUY_X_GET_Y / QTY_PRICE stay in the type, unused.