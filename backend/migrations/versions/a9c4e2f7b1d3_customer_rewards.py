"""customers, reward points passbook, reward columns on sales

Revision ID: a9c4e2f7b1d3
Revises: e7f9a1c3b5d2, 17b2cccb514b (also merges main's two migration heads)
Create Date: 2026-10-09
"""
from alembic import op
import sqlalchemy as sa


revision = "a9c4e2f7b1d3"
down_revision = ("e7f9a1c3b5d2", "17b2cccb514b")
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mobile", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("points_balance", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lifetime_earned", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lifetime_redeemed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_spent", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("visit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("first_visit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_visit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("points_balance >= 0", name="points_not_negative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mobile"),
    )
    op.create_table(
        "reward_transactions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=True),
        sa.Column("return_id", sa.Integer(), nullable=True),
        sa.Column("txn_type", sa.Enum("EARN", "REDEEM", "REVERSE", "ADJUST", name="reward_txn_type"), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("points <> 0", name="reward_points_not_zero"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["sale_id"], ["sales.id"]),
        sa.ForeignKeyConstraint(["return_id"], ["sale_returns.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("reward_transactions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_reward_transactions_customer_id"), ["customer_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_reward_transactions_sale_id"), ["sale_id"], unique=False)

    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.add_column(sa.Column("customer_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("points_redeemed", sa.Integer(), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("reward_discount", sa.Numeric(12, 2), server_default="0", nullable=False))
        batch_op.add_column(sa.Column("points_earned", sa.Integer(), server_default="0", nullable=False))
        batch_op.create_index(batch_op.f("ix_sales_customer_id"), ["customer_id"], unique=False)
        batch_op.create_foreign_key(batch_op.f("fk_sales_customer_id_customers"), "customers", ["customer_id"], ["id"])

    with op.batch_alter_table("sale_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("reward_discount", sa.Numeric(12, 2), server_default="0", nullable=False))


def downgrade():
    with op.batch_alter_table("sale_items", schema=None) as batch_op:
        batch_op.drop_column("reward_discount")
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_sales_customer_id_customers"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_sales_customer_id"))
        batch_op.drop_column("points_earned")
        batch_op.drop_column("reward_discount")
        batch_op.drop_column("points_redeemed")
        batch_op.drop_column("customer_id")
    op.drop_table("reward_transactions")
    op.drop_table("customers")
    sa.Enum(name="reward_txn_type").drop(op.get_bind(), checkfirst=True)
