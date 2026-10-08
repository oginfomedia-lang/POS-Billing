"""PaymentIntent: one Razorpay attempt (UPI QR or card-machine push) for a sale."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import PaymentIntentStatus, PaymentMethod


class PaymentIntent(TimestampMixin, db.Model):
    __tablename__ = "payment_intents"

    id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True)
    method = db.Column(db.Enum(PaymentMethod, name="payment_method"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)          # exact bill total when created
    status = db.Column(db.Enum(PaymentIntentStatus, name="payment_intent_status"),
                       nullable=False, default=PaymentIntentStatus.PENDING)
    provider_ref = db.Column(db.String(64), nullable=False, index=True)  # QR id (qr_xxx) or p2pRequestId
    provider_txn_id = db.Column(db.String(100), nullable=True)           # Razorpay payment id / card txn id
    qr_image_url = db.Column(db.Text, nullable=True)                     # UPI only
    failure_reason = db.Column(db.String(255), nullable=True)

    sale = db.relationship("Sale")