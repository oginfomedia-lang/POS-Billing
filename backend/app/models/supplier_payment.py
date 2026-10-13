"""SupplierPayment and SupplierPaymentAllocation: accounts-payable payments."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import SupplierPaymentMethod, SupplierPaymentType


class SupplierPayment(TimestampMixin, db.Model):
    __tablename__ = "supplier_payments"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("suppliers.id"), nullable=False, index=True
    )
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)

    payment_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    payment_type = db.Column(
        db.Enum(SupplierPaymentType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SupplierPaymentType.PAYMENT,
    )
    payment_method = db.Column(
        db.Enum(SupplierPaymentMethod, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=SupplierPaymentMethod.BANK_TRANSFER,
    )
    reference_number = db.Column(db.String(100), nullable=True)
    bank_account = db.Column(db.String(200), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_voided = db.Column(db.Boolean, nullable=False, default=False)
    voided_at = db.Column(db.DateTime(timezone=True), nullable=True)
    voided_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    supplier = db.relationship("Supplier")
    store = db.relationship("Store")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    voided_by = db.relationship("User", foreign_keys=[voided_by_id])
    allocations = db.relationship(
        "SupplierPaymentAllocation",
        back_populates="payment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<SupplierPayment {self.id} supplier={self.supplier_id} amount={self.amount}>"


class SupplierPaymentAllocation(db.Model):
    """Links a payment to one or more supplier invoices."""

    __tablename__ = "supplier_payment_allocations"

    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(
        db.Integer,
        db.ForeignKey("supplier_payments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    invoice_id = db.Column(
        db.Integer, db.ForeignKey("supplier_invoices.id"), nullable=False, index=True
    )
    allocated_amount = db.Column(db.Numeric(12, 2), nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "payment_id", "invoice_id", name="uq_supplier_payment_allocations"
        ),
    )

    payment = db.relationship("SupplierPayment", back_populates="allocations")
    invoice = db.relationship("SupplierInvoice")
