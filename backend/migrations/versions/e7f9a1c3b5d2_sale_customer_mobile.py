"""optional customer mobile number on bills

Revision ID: e7f9a1c3b5d2
Revises: d5e8f3b1a2c4
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa


revision = "e7f9a1c3b5d2"
down_revision = "d5e8f3b1a2c4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("sales", sa.Column("customer_mobile", sa.String(length=10), nullable=True))
    with op.batch_alter_table("sales", schema=None) as batch_op:
        # find a customer's bills by mobile (returns without a receipt)
        batch_op.create_index(batch_op.f("ix_sales_customer_mobile"), ["customer_mobile"], unique=False)


def downgrade():
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_sales_customer_mobile"))
    op.drop_column("sales", "customer_mobile")
