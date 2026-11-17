"""customer udhari: a cash repayment taken at a counter belongs to that cashier's shift (it is in the drawer)

Revision ID: e1c4b7a9d2f3
Revises: d8f2a1b4e5c6
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa

revision = "e1c4b7a9d2f3"
down_revision = "d8f2a1b4e5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("credit_transactions", sa.Column("shift_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_credit_transactions_shift_id_cashier_shifts", "credit_transactions", "cashier_shifts",
        ["shift_id"], ["id"],
    )
    op.create_index("ix_credit_transactions_shift_id", "credit_transactions", ["shift_id"])
    op.create_index("ix_credit_transactions_return_id", "credit_transactions", ["return_id"])


def downgrade():
    op.drop_index("ix_credit_transactions_return_id", table_name="credit_transactions")
    op.drop_index("ix_credit_transactions_shift_id", table_name="credit_transactions")
    op.drop_constraint("fk_credit_transactions_shift_id_cashier_shifts", "credit_transactions", type_="foreignkey")
    op.drop_column("credit_transactions", "shift_id")
