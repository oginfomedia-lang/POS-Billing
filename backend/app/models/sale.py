"""Sale, SaleItem (historical name/price snapshot) and BillSequence models."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import SaleStatus


class Sale(TimestampMixin, db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(40), unique=True, nullable=True)  # assigned on completion
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    counter_id = db.Column(db.Integer, db.ForeignKey("counters.id"), nullable=False)
    shift_id = db.Column(db.Integer, db.ForeignKey("cashier_shifts.id"), nullable=False, index=True)
    cashier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(
        db.Enum(SaleStatus, name="sale_status"), nullable=False, default=SaleStatus.OPEN, index=True
    )
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(255), nullable=True)  # hold note
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    items = db.relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan", order_by="SaleItem.id"
    )
    payments = db.relationship(
        "Payment", back_populates="sale", cascade="all, delete-orphan", order_by="Payment.id"
    )
    store = db.relationship("Store")
    counter = db.relationship("Counter")
    cashier = db.relationship("User")

    def __repr__(self) -> str:
        return f"<Sale {self.id} {self.bill_number or 'draft'} ({self.status.value})>"


class SaleItem(TimestampMixin, db.Model):
    __tablename__ = "sale_items"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    # Snapshots: the bill keeps the name/price/tax as they were at sale time.
    product_name = db.Column(db.String(200), nullable=False)
    unit_price = db.Column(db.Numeric(12, 2), nullable=False)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    qty = db.Column(db.Integer, nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)  # unit_price * qty, before tax
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    sale = db.relationship("Sale", back_populates="items")

    def __repr__(self) -> str:
        return f"<SaleItem {self.product_name} x{self.qty}>"


class BillSequence(db.Model):
    __tablename__ = "bill_sequences"

    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), primary_key=True)
    last_number = db.Column(db.Integer, nullable=False, default=0)
