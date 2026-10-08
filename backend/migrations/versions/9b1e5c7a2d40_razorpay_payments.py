"""razorpay payments: card machine per counter + payment_intents table

Revision ID: 9b1e5c7a2d40
Revises: b5d2e8f1a3c7
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "9b1e5c7a2d40"
down_revision = "b5d2e8f1a3c7"  # store_price_override (copied from issues-in-offers-and-branch-switch in Step 1)
branch_labels = None
depends_on = None


# Already exists in the database (created by e9629c99c2ef for the payments table).
# create_type=False = "just use it, don't try to CREATE TYPE again".
payment_method = postgresql.ENUM("CASH", "CARD", "UPI", "SPLIT", name="payment_method", create_type=False)

# Brand new type for this migration.
payment_intent_status = postgresql.ENUM(
    "PENDING", "PAID", "FAILED", "CANCELLED", name="payment_intent_status", create_type=False
)


def upgrade():
    # 1) Card machine ID on each counter. Nullable: existing counters simply have no machine yet.
    op.add_column("counters", sa.Column("edc_device_id", sa.String(length=100), nullable=True))

    # 2) New enum type. checkfirst=True = skip if it already exists (safe to re-run after a failed attempt).
    payment_intent_status.create(op.get_bind(), checkfirst=True)

    # 3) The payment_intents table: one row per Razorpay QR / card-machine push.
    op.create_table(
        "payment_intents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sale_id", sa.Integer(), nullable=False),
        sa.Column("method", payment_method, nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", payment_intent_status, nullable=False),
        sa.Column("provider_ref", sa.String(length=64), nullable=False),
        sa.Column("provider_txn_id", sa.String(length=100), nullable=True),
        sa.Column("qr_image_url", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sale_id"], ["sales.id"],
            name=op.f("fk_payment_intents_sale_id_sales"),
            ondelete="CASCADE",          # deleting a sale deletes its payment attempts
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_intents")),
    )
    with op.batch_alter_table("payment_intents", schema=None) as batch_op:
        # "all attempts for this bill" — used to cancel pending ones when the cart changes
        batch_op.create_index(batch_op.f("ix_payment_intents_sale_id"), ["sale_id"], unique=False)
        # look up an attempt by Razorpay's id (qr_xxx / p2pRequestId)
        batch_op.create_index(batch_op.f("ix_payment_intents_provider_ref"), ["provider_ref"], unique=False)


def downgrade():
    # Undo in reverse order.
    with op.batch_alter_table("payment_intents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payment_intents_provider_ref"))
        batch_op.drop_index(batch_op.f("ix_payment_intents_sale_id"))
    op.drop_table("payment_intents")

    # Only OUR new type. Never drop payment_method — the payments table still uses it.
    sa.Enum(name="payment_intent_status").drop(op.get_bind(), checkfirst=True)

    op.drop_column("counters", "edc_device_id")