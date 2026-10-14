"""SaleReturn (one credit note) and SaleReturnItem (one returned line). Refunds are paid in cash."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import PaymentMethod


class SaleReturn(TimestampMixin, db.Model):
    __tablename__ = "sale_returns"

    id = db.Column(db.Integer, primary_key=True)
    return_number = db.Column(db.String(40), unique=True, nullable=True)  # set right after insert: RT01-261008-00012
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=False, index=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    # The shift whose drawer paid the cash out (not the original bill's shift).
    shift_id = db.Column(db.Integer, db.ForeignKey("cashier_shifts.id"), nullable=False, index=True)
    cashier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    refund_method = db.Column(
        db.Enum(PaymentMethod, name="payment_method"), nullable=False, default=PaymentMethod.CASH
    )
    # The returned share of the original lines (before GST), and the cash given back (incl. GST).
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    refund_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    items = db.relationship(
        "SaleReturnItem", back_populates="sale_return", cascade="all, delete-orphan", order_by="SaleReturnItem.id"
    )
    sale = db.relationship("Sale")
    store = db.relationship("Store")
    cashier = db.relationship("User", foreign_keys=[cashier_id])
    approved_by = db.relationship("User", foreign_keys=[approved_by_id])

    __table_args__ = (db.CheckConstraint("refund_amount >= 0", name="refund_not_negative"),)

    def __repr__(self) -> str:
        return f"<SaleReturn {self.return_number or self.id} ₹{self.refund_amount}>"


class SaleReturnItem(db.Model):
    __tablename__ = "sale_return_items"

    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey("sale_returns.id", ondelete="CASCADE"), nullable=False, index=True)
    sale_item_id = db.Column(db.Integer, db.ForeignKey("sale_items.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    # Snapshots for the credit note.
    product_name = db.Column(db.String(200), nullable=False)
    hsn_code = db.Column(db.String(8), nullable=True)
    tax_rate = db.Column(db.Numeric(5, 2), nullable=False, default=0)
    qty = db.Column(db.Numeric(12, 3), nullable=False)
    line_total = db.Column(db.Numeric(12, 2), nullable=False)  # share of the original line, before discount
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    tax_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    refund_amount = db.Column(db.Numeric(12, 2), nullable=False)  # line - discount + tax
    restocked = db.Column(db.Boolean, nullable=False, default=True)  # False = damaged, not put back on the shelf
    unit_cost = db.Column(db.Numeric(12, 4), nullable=True)  # copied from the sale item: the return reverses it

    sale_return = db.relationship("SaleReturn", back_populates="items")

    __table_args__ = (db.CheckConstraint("qty > 0", name="qty_positive"),)
