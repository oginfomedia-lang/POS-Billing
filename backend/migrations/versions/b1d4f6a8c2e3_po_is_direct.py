"""purchase orders: is_direct (goods arrived without a PO; entered from the supplier's bill)

Revision ID: b1d4f6a8c2e3
Revises: a9c3e5f7b1d2
Create Date: 2026-11-17
"""
from alembic import op
import sqlalchemy as sa

revision = "b1d4f6a8c2e3"
down_revision = "a9c3e5f7b1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("purchase_orders", sa.Column("is_direct", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("purchase_orders", "is_direct")
