"""CashierShift model (opening/expected/actual cash, status)."""
from app.extensions import db
from app.models.base import TimestampMixin, _now
from app.models.enums import ShiftStatus


class CashierShift(TimestampMixin, db.Model):
    __tablename__ = "cashier_shifts"

    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    counter_id = db.Column(db.Integer, db.ForeignKey("counters.id"), nullable=False)
    cashier_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(
        db.Enum(ShiftStatus, name="shift_status"), nullable=False, default=ShiftStatus.OPEN
    )
    opening_cash = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expected_cash = db.Column(db.Numeric(12, 2), nullable=True)
    actual_cash = db.Column(db.Numeric(12, 2), nullable=True)
    opened_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    store = db.relationship("Store")
    counter = db.relationship("Counter")
    cashier = db.relationship("User")

    def __repr__(self) -> str:
        return f"<CashierShift {self.id} ({self.status.value})>"
