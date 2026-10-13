"""SupplierInvoice: tracks bills received from suppliers."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import InvoiceVerificationStatus, SupplierInvoiceStatus


class SupplierInvoice(TimestampMixin, db.Model):
    __tablename__ = "supplier_invoices"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("suppliers.id"), nullable=False, index=True
    )
    purchase_order_id = db.Column(
        db.Integer, db.ForeignKey("purchase_orders.id"), nullable=True, index=True
    )
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)

    invoice_number = db.Column(db.String(100), nullable=False)
    invoice_date = db.Column(db.Date, nullable=False)
    due_date = db.Column(db.Date, nullable=True)

    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    other_charges = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    grand_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    amount_paid = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    payment_status = db.Column(
        db.Enum(SupplierInvoiceStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SupplierInvoiceStatus.UNPAID,
        index=True,
    )
    verification_status = db.Column(
        db.Enum(InvoiceVerificationStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=InvoiceVerificationStatus.PENDING,
    )

    notes = db.Column(db.Text, nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        db.UniqueConstraint(
            "supplier_id", "invoice_number", name="uq_supplier_invoices_supplier_invoice_number"
        ),
    )

    supplier = db.relationship("Supplier")
    purchase_order = db.relationship("PurchaseOrder")
    store = db.relationship("Store")
    created_by = db.relationship("User")
    grn_links = db.relationship(
        "SupplierInvoiceGRN", back_populates="invoice", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SupplierInvoice {self.invoice_number} supplier={self.supplier_id}>"


class SupplierInvoiceGRN(db.Model):
    """Junction: links a supplier invoice to one or more GRNs."""

    __tablename__ = "supplier_invoice_grns"

    id = db.Column(db.Integer, primary_key=True)
    supplier_invoice_id = db.Column(
        db.Integer,
        db.ForeignKey("supplier_invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    goods_receipt_id = db.Column(
        db.Integer, db.ForeignKey("goods_receipts.id"), nullable=False
    )

    __table_args__ = (
        db.UniqueConstraint(
            "supplier_invoice_id",
            "goods_receipt_id",
            name="uq_supplier_invoice_grns",
        ),
    )

    invoice = db.relationship("SupplierInvoice", back_populates="grn_links")
    goods_receipt = db.relationship("GoodsReceipt")
