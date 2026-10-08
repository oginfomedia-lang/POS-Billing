"""add expiry_date to inventory_transactions

Revision ID: a1b2c3d4e5f6
Revises: f91a2048d011
Create Date: 2026-10-08

"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f91a2048d011'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inventory_transactions",
        sa.Column("expiry_date", sa.Date, nullable=True),
    )


def downgrade():
    op.drop_column("inventory_transactions", "expiry_date")
