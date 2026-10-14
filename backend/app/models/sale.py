"""Sale, SaleItem (historical name/price snapshot) and BillSequence models."""
from decimal import Decimal

from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import SaleStatus


class Sale(TimestampMixin, db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    bill_number = db.Column(db.String(40), unique=True, nullable=True)  # assigned on completion
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    counter_id = db.Column(db.Integer, db.ForeignKey("counters.id"), nullable=True)  # shifts may have no counter
    shift_id = db.Column(db.Integer, db.ForeignKey("cashier_shifts.id"), nullable=False, index=True)
    cashier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(
        db.Enum(SaleStatus, name="sale_status"), nullable=False, default=SaleStatus.OPEN, index=True
    )
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    bill_offer_id = db.Column(db.Integer, db.ForeignKey("discounts.id"), nullable=True)
    bill_offer_name = db.Column(db.String(100), nullable=True)  # snapshot for receipt/reports
    bill_offer_discount = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.String(255), nullable=True)  # hold note
    customer_mobile = db.Column(db.String(10), nullable=True, index=True)  # optional, 10-digit Indian mobile
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)  # set when paid
    points_redeemed = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    reward_discount = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    points_earned = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    items = db.relationship(
        "SaleItem", back_populates="sale", cascade="all, delete-orphan", order_by="SaleItem.id"
    )
    payments = db.relationship(
        "Payment", back_populates="sale", cascade="all, delete-orphan", order_by="Payment.id"
    )
    customer = db.relationship("Customer")
    store = db.relationship("Store")
    counter = db.relationship("Counter")
    cashier = db.relationship("User")

    @property
    def total_saving(self) -> Decimal:
        """"You saved" on the bill: MRP vs what the customer paid, plus offers on items without an MRP."""
        return sum((i.saving for i in self.items), Decimal("0.00"))

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
    mrp = db.Column(db.Numeric(12, 2), nullable=True)  # incl. GST, per unit
    hsn_code = db.Column(db.String(8), nullable=True)
    qty = db.Column(db.Numeric(12, 3), nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)  # unit_price * qty, before discount and tax
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    # discount_amount = offer_discount + manual_discount + reward_discount + this line's share of the bill offer.
    offer_id = db.Column(db.Integer, db.ForeignKey("discounts.id"), nullable=True)
    reward_discount = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    offer_name = db.Column(db.String(100), nullable=True)  # snapshot for cart/receipt/reports
    offer_discount = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    manual_discount = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    manual_discount_reason = db.Column(db.String(100), nullable=True)
    manual_discount_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)  # on (line_total - discount_amount)
    unit_cost = db.Column(db.Numeric(12, 4), nullable=True)  # purchase cost per unit when paid (profit report)

    sale = db.relationship("Sale", back_populates="items")
    product = db.relationship("Product")

    @property
    def saving(self) -> Decimal:
        from app.services.pricing_service import line_saving
        return line_saving(self.mrp, self.qty, self.line_total, self.discount_amount, self.tax_amount)

    @property
    def is_variable_weight(self) -> bool:
        """Loose item sold by weight (qty is kg)."""
        return bool(self.product and self.product.is_variable_weight)

    @property
    def uom(self) -> str:
        return self.product.uom.value if self.product and self.product.uom else "pcs"

    def __repr__(self) -> str:
        return f"<SaleItem {self.product_name} x{self.qty}>"


class BillSequence(db.Model):
    __tablename__ = "bill_sequences"

    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), primary_key=True)
    last_number = db.Column(db.Integer, nullable=False, default=0)
