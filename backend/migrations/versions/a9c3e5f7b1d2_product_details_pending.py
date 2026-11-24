"""products: details_pending (typed on a purchase order; no selling price / GST / MRP yet, billing refuses it)

Revision ID: a9c3e5f7b1d2
Revises: f2d5c8e1a7b4
Create Date: 2026-11-17
"""
from alembic import op
import sqlalchemy as sa

revision = "a9c3e5f7b1d2"
down_revision = "f2d5c8e1a7b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("details_pending", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("products", "details_pending")
