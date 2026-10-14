"""Inventory (stock per store+product, CHECK qty >= 0) and InventoryTransaction (stock ledger)."""
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
