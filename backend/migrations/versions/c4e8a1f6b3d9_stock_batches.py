"""stock_batches + sale_item_batches: batch-wise stock, sold earliest expiry first

Revision ID: c4e8a1f6b3d9
Revises: b9d3e7f2a6c4
Create Date: 2026-10-21

Existing stock becomes batches. The stock on hand is assumed to be what arrived last: it is matched to the most
recent stock-in rows of the ledger (newest first) with their expiry dates, and the goods receipt's batch number
when there is one. Whatever isn't covered by those rows becomes one batch without an expiry date.
"""
from datetime import datetime, timezone
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

from app.utils.migration_guards import has_table


revision = "c4e8a1f6b3d9"
down_revision = "b9d3e7f2a6c4"
branch_labels = None
depends_on = None


def upgrade():
    if has_table("stock_batches"):
        return  # already there (with its batches): nothing to add
    op.create_table(
        "stock_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("batch_number", sa.String(length=100), nullable=True),
        sa.Column("mfg_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("qty_received", sa.Numeric(12, 3), nullable=False),
        sa.Column("qty_remaining", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("qty_remaining >= 0", name="ck_stock_batches_remaining_non_negative"),
    )
    op.create_index("ix_stock_batches_store_product_expiry", "stock_batches", ["store_id", "product_id", "expiry_date"])
    op.create_table(
        "sale_item_batches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sale_item_id", sa.Integer(), sa.ForeignKey("sale_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("stock_batches.id"), nullable=False),
        sa.Column("qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("qty_returned", sa.Numeric(12, 3), nullable=False, server_default="0"),
    )
    op.create_index("ix_sale_item_batches_sale_item_id", "sale_item_batches", ["sale_item_id"])
    op.create_index("ix_sale_item_batches_batch_id", "sale_item_batches", ["batch_id"])

    _batches_from_current_stock(op.get_bind())


def _batches_from_current_stock(conn) -> None:
    stock = conn.execute(sa.text(
        "SELECT store_id, product_id, qty_on_hand, avg_cost FROM inventory WHERE qty_on_hand > 0"
    )).all()
    insert = sa.text(
        "INSERT INTO stock_batches (store_id, product_id, batch_number, mfg_date, expiry_date, qty_received, "
        "qty_remaining, unit_cost, source, reference_id, received_at) "
        "VALUES (:s, :p, :bn, :mfg, :exp, :q, :q, :cost, 'migration', :ref, :at)"
    )
    for store_id, product_id, on_hand, avg_cost in stock:
        left = Decimal(on_hand)
        arrivals = conn.execute(sa.text(
            """
            SELECT t.qty, t.expiry_date, t.created_at, t.reference_id,
                   upper(t.txn_type::text) = 'PURCHASE' AS is_purchase
            FROM inventory_transactions t
            WHERE t.store_id = :s AND t.product_id = :p AND t.qty > 0
              AND (upper(t.txn_type::text) = 'PURCHASE' OR t.expiry_date IS NOT NULL)
            ORDER BY t.created_at DESC, t.id DESC
            """
        ), {"s": store_id, "p": product_id}).all()
        for qty, expiry, created_at, ref, is_purchase in arrivals:
            if left <= 0:
                break
            part = min(Decimal(qty), left)
            batch_number = mfg = None
            if is_purchase and ref is not None:  # a goods receipt: reference_id = goods_receipts.id
                row = conn.execute(sa.text(
                    "SELECT batch_number, mfg_date FROM goods_receipt_items "
                    "WHERE goods_receipt_id = :r AND product_id = :p ORDER BY id LIMIT 1"
                ), {"r": ref, "p": product_id}).first()
                if row is not None:
                    batch_number, mfg = row
            conn.execute(insert, {"s": store_id, "p": product_id, "bn": batch_number, "mfg": mfg, "exp": expiry,
                                  "q": part, "cost": avg_cost, "ref": ref if is_purchase else None, "at": created_at})
            left -= part
        if left > 0:
            conn.execute(insert, {"s": store_id, "p": product_id, "bn": None, "mfg": None, "exp": None,
                                  "q": left, "cost": avg_cost, "ref": None, "at": datetime.now(timezone.utc)})


def downgrade():
    op.drop_table("sale_item_batches")
    op.drop_table("stock_batches")
