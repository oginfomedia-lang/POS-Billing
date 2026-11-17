"""customer udhari: credit balance, limit and khata passbook table

Revision ID: d8f2a1b4e5c6
Revises: c7e3a9b2d4f1
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d8f2a1b4e5c6"
down_revision = "c7e3a9b2d4f1"
branch_labels = None
depends_on = None


credit_txn_type = postgresql.ENUM("UDHARI", "PAYMENT", "RETURN", "ADJUST", name="credit_txn_type", create_type=False)


def upgrade():
    # 1. Add CREDIT value to existing payment_method postgres enum
    op.execute("ALTER TYPE payment_method ADD VALUE IF NOT EXISTS 'CREDIT'")

    # 2. Add credit_txn_type enum type
    credit_txn_type.create(op.get_bind(), checkfirst=True)

    # 3. Add credit_balance and credit_limit to customers table
    op.add_column("customers", sa.Column("credit_balance", sa.Numeric(12, 2), nullable=False, server_default="0"))
    op.add_column("customers", sa.Column("credit_limit", sa.Numeric(12, 2), nullable=True))

    # 4. Create credit_transactions table
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("sale_id", sa.Integer(), sa.ForeignKey("sales.id"), nullable=True),
        sa.Column("return_id", sa.Integer(), sa.ForeignKey("sale_returns.id"), nullable=True),
        sa.Column("txn_type", credit_txn_type, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("amount <> 0", name="ck_credit_txn_amount_not_zero"),
    )
    op.create_index("ix_credit_transactions_customer_id", "credit_transactions", ["customer_id"])
    op.create_index("ix_credit_transactions_store_id", "credit_transactions", ["store_id"])
    op.create_index("ix_credit_transactions_sale_id", "credit_transactions", ["sale_id"])


def downgrade():
    op.drop_table("credit_transactions")
    op.drop_column("customers", "credit_limit")
    op.drop_column("customers", "credit_balance")
    credit_txn_type.drop(op.get_bind(), checkfirst=True)