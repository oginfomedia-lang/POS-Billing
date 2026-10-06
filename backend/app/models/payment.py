"""Payment model (CASH/CARD/UPI rows; many per sale for MIXED)."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import PaymentMethod


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    method = db.Column(db.Enum(PaymentMethod, name="payment_method"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)  # amount applied to the bill
    reference = db.Column(db.String(100), nullable=True)  # card slip / UPI txn id
    tendered = db.Column(db.Numeric(12, 2), nullable=True)  # cash handed over (cash only)
    change_due = db.Column(db.Numeric(12, 2), nullable=True)  # cash returned (cash only)

    sale = db.relationship("Sale", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment {self.method.value} {self.amount}>"
