"""per-store selling price: inventory.price overrides products.price for that store

Revision ID: b5d2e8f1a3c7
Revises: ecbbe01d63aa
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa


revision = "b5d2e8f1a3c7"
down_revision = "ecbbe01d63aa"
branch_labels = None
depends_on = None


def upgrade():
    # NULL = the store sells at the head-office price (products.price).
    op.add_column("inventory", sa.Column("price", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint(op.f("ck_inventory_price_non_negative"), "inventory", "price IS NULL OR price >= 0")


def downgrade():
    op.drop_constraint(op.f("ck_inventory_price_non_negative"), "inventory", type_="check")
    op.drop_column("inventory", "price")
