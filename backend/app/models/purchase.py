"""PurchaseOrder, PurchaseOrderItem, GoodsReceipt, GoodsReceiptItem models."""
from datetime import datetime, timezone

from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import PurchaseStatus


def _now():
    return datetime.now(timezone.utc)


class PurchaseOrder(TimestampMixin, db.Model):
    __tablename__ = "purchase_orders"

    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)
    purchase_date = db.Column(db.Date, nullable=False)
    expected_delivery_date = db.Column(db.Date, nullable=True)
    reference_number = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    internal_remarks = db.Column(db.Text, nullable=True)

    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    grand_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    status = db.Column(
        db.Enum(PurchaseStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=PurchaseStatus.DRAFT,
        index=True,
    )

    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    ordered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    ordered_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    cancelled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    cancelled_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    supplier = db.relationship("Supplier", foreign_keys=[supplier_id])
    store = db.relationship("Store", foreign_keys=[store_id])
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    ordered_by = db.relationship("User", foreign_keys=[ordered_by_id])
    cancelled_by = db.relationship("User", foreign_keys=[cancelled_by_id])
    items = db.relationship(
        "PurchaseOrderItem",
        back_populates="purchase_order",
        cascade="all, delete-orphan",
        order_by="PurchaseOrderItem.id",
    )
    receipts = db.relationship(
        "GoodsReceipt",
        back_populates="purchase_order",
        order_by="GoodsReceipt.id",
    )

    def __repr__(self):
        return f"<PurchaseOrder {self.po_number} ({self.status.value})>"


class PurchaseOrderItem(db.Model):
    __tablename__ = "purchase_order_items"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(
        db.Integer,
        db.ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)
    product_sku = db.Column(db.String(50), nullable=True)

    ordered_qty = db.Column(db.Numeric(12, 3), nullable=False)
    received_qty = db.Column(db.Numeric(12, 3), nullable=False, default=0)

    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount_percent = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    line_discount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    # gross amount: ordered_qty × unit_price (before discount and tax)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)

    purchase_order = db.relationship("PurchaseOrder", back_populates="items")
    product = db.relationship("Product")

    def __repr__(self):
        return f"<POItem {self.product_name} x{self.ordered_qty}>"


class GoodsReceipt(TimestampMixin, db.Model):
    __tablename__ = "goods_receipts"

    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(
        db.Integer, db.ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    receipt_number = db.Column(db.String(40), unique=True, nullable=False)
    received_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    received_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)

    purchase_order = db.relationship("PurchaseOrder", back_populates="receipts")
    received_by = db.relationship("User")
    receipt_items = db.relationship(
        "GoodsReceiptItem",
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="GoodsReceiptItem.id",
    )

    def __repr__(self):
        return f"<GoodsReceipt {self.receipt_number}>"


class GoodsReceiptItem(db.Model):
    __tablename__ = "goods_receipt_items"

    id = db.Column(db.Integer, primary_key=True)
    goods_receipt_id = db.Column(
        db.Integer,
        db.ForeignKey("goods_receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_item_id = db.Column(
        db.Integer, db.ForeignKey("purchase_order_items.id"), nullable=False
    )
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    qty_received = db.Column(db.Numeric(12, 3), nullable=False)
    expiry_date = db.Column(db.Date, nullable=True)

    receipt = db.relationship("GoodsReceipt", back_populates="receipt_items")
    purchase_order_item = db.relationship("PurchaseOrderItem")
    product = db.relationship("Product")

    def __repr__(self):
        return f"<GRItem product={self.product_id} qty={self.qty_received}>"
