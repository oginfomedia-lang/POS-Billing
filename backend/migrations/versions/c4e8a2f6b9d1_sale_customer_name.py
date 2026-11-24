"""sales: customer_name (typed at the counter; optional, but needed with the mobile for a bill on udhari)

Revision ID: c4e8a2f6b9d1
Revises: b1d4f6a8c2e3
Create Date: 2026-11-17

When the bill is paid the name is also saved on the customer (customers.name).
"""
from alembic import op
import sqlalchemy as sa


revision = "c4e8a2f6b9d1"
down_revision = "b1d4f6a8c2e3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sales", sa.Column("customer_name", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("sales", "customer_name")
