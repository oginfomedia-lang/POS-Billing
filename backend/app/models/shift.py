"""CashierShift model (opening/expected/actual cash, status)."""
from datetime import datetime, timezone

from app.extensions import db
from app.models.enums import ShiftStatus


class CashierShift(db.Model):
    __tablename__ = "cashier_shifts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    counter_id = db.Column(db.Integer, db.ForeignKey("counters.id"), nullable=True)
    status = db.Column(
        db.Enum(ShiftStatus, name="shift_status"), nullable=False, default=ShiftStatus.OPEN
    )
    opening_float = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    expected_cash = db.Column(db.Numeric(12, 2), nullable=True)
    actual_cash = db.Column(db.Numeric(12, 2), nullable=True)
    opened_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    closed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = db.relationship("User")
    store = db.relationship("Store")
    counter = db.relationship("Counter")

    def __repr__(self) -> str:
        return f"<CashierShift user={self.user_id} status={self.status.value}>"
