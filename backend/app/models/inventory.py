"""Inventory (stock per store+product, CHECK qty >= 0), InventoryTransaction (stock ledger), StockBatch (the lots
that stock is made of) and SaleItemBatch (which lots a bill line took)."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.extensions import db
from app.models.enums import InventoryTxnType


class Inventory(db.Model):
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("store_id", "product_id", name="uq_inventory_store_product"),
        CheckConstraint("qty_on_hand >= 0", name="ck_inventory_qty_non_negative"),
        CheckConstraint("price IS NULL OR price >= 0", name="ck_inventory_price_non_negative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty_on_hand = db.Column(db.Numeric(12, 3), nullable=False, default=0)
    low_stock_threshold = db.Column(db.Numeric(12, 3), nullable=True)
    # This store's own selling price (before GST). NULL = use the head-office price (products.price).
    price = db.Column(db.Numeric(12, 2), nullable=True)
    # Weighted-average purchase cost (before GST), updated on each goods receipt. NULL = products.cost_price.
    avg_cost = db.Column(db.Numeric(12, 4), nullable=True)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    store = db.relationship("Store")
    product = db.relationship("Product", back_populates="inventory")

    def __repr__(self) -> str:
        return f"<Inventory product={self.product_id} store={self.store_id} qty={self.qty_on_hand}>"


class InventoryTransaction(db.Model):
    __tablename__ = "inventory_transactions"

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    txn_type = db.Column(db.Enum(InventoryTxnType, name="inventory_txn_type"), nullable=False)
    qty = db.Column(db.Numeric(12, 3), nullable=False)
    reference_id = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    store = db.relationship("Store")
    product = db.relationship("Product")

    def __repr__(self) -> str:
        return f"<InventoryTxn {self.txn_type.value} product={self.product_id} qty={self.qty}>"


class StockBatch(db.Model):
    """One lot of a product in a store (a goods receipt line, a stock-in, opening stock...). The batches' qty_remaining
    always add up to Inventory.qty_on_hand: every stock change goes through services/batch_service.py.
    Sales take from the batch that expires first (FEFO)."""

    __tablename__ = "stock_batches"
    __table_args__ = (
        CheckConstraint("qty_remaining >= 0", name="ck_stock_batches_remaining_non_negative"),
        db.Index("ix_stock_batches_store_product_expiry", "store_id", "product_id", "expiry_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    batch_number = db.Column(db.String(100), nullable=True)  # as printed on the pack (supplier's lot number)
    mfg_date = db.Column(db.Date, nullable=True)
    expiry_date = db.Column(db.Date, nullable=True)  # NULL = doesn't expire / not recorded: sold last
    qty_received = db.Column(db.Numeric(12, 3), nullable=False)
    qty_remaining = db.Column(db.Numeric(12, 3), nullable=False)
    unit_cost = db.Column(db.Numeric(12, 4), nullable=True)  # purchase cost before GST, when known
    # grn / stock_in / opening / return / adjustment / migration
    source = db.Column(db.String(20), nullable=False)
    reference_id = db.Column(db.Integer, nullable=True)  # goods receipt / return id, by source
    received_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    product = db.relationship("Product")

    def __repr__(self) -> str:
        return f"<StockBatch {self.batch_number or self.id} product={self.product_id} left={self.qty_remaining}>"


class SaleItemBatch(db.Model):
    """Which batches a bill line was taken from, so a return goes back to the same batch (and a recall can find
    who bought a batch)."""

    __tablename__ = "sale_item_batches"

    id = db.Column(db.Integer, primary_key=True)
    sale_item_id = db.Column(
        db.Integer, db.ForeignKey("sale_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id = db.Column(db.Integer, db.ForeignKey("stock_batches.id"), nullable=False, index=True)
    qty = db.Column(db.Numeric(12, 3), nullable=False)
    qty_returned = db.Column(db.Numeric(12, 3), nullable=False, default=0, server_default="0")

    batch = db.relationship("StockBatch")
