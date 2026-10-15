"""cost price for the profit report: product default cost, per-store average cost, cost on bills and returns

Revision ID: a7c3e9f1b2d4
Revises: e5a8c1f3b7d2
Create Date: 2026-10-14

Bills made before this migration have no unit_cost; the profit report falls back to the current cost for them.
"""
from alembic import op
import sqlalchemy as sa


revision = "a7c3e9f1b2d4"
down_revision = "e5a8c1f3b7d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("cost_price", sa.Numeric(12, 4), nullable=True))
    op.add_column("inventory", sa.Column("avg_cost", sa.Numeric(12, 4), nullable=True))
    op.add_column("sale_items", sa.Column("unit_cost", sa.Numeric(12, 4), nullable=True))
    op.add_column("sale_return_items", sa.Column("unit_cost", sa.Numeric(12, 4), nullable=True))


def downgrade():
    op.drop_column("sale_return_items", "unit_cost")
    op.drop_column("sale_items", "unit_cost")
    op.drop_column("inventory", "avg_cost")
    op.drop_column("products", "cost_price")
