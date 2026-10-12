"""Customer (one per mobile number, with a points balance) and RewardTransaction (the points passbook).

customers.points_balance is a running total for quick lookups; every change to it is also written to
reward_transactions (by CustomerRepository.add_txn only), so the balance can always be checked against
its history.
"""
from datetime import datetime, timezone

from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import RewardTxnType


class Customer(TimestampMixin, db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    # Same 10-digit format as sales.customer_mobile (utils/phone.normalize_mobile). UNIQUE: one customer per number.
    mobile = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)  # optional, added later from the admin screen
    points_balance = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    lifetime_earned = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    lifetime_redeemed = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    total_spent = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")  # paid bills, incl. GST
    visit_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")  # number of paid bills
    first_visit_at = db.Column(db.DateTime(timezone=True), nullable=True)  # = registration (first paid bill)
    last_visit_at = db.Column(db.DateTime(timezone=True), nullable=True)

    transactions = db.relationship(
        "RewardTransaction", back_populates="customer", order_by="RewardTransaction.id.desc()", lazy="dynamic"
    )

    # The database itself refuses a negative balance, even if a code bug tried to spend too much.
    __table_args__ = (db.CheckConstraint("points_balance >= 0", name="points_not_negative"),)

    def __repr__(self) -> str:
        return f"<Customer {self.mobile} {self.points_balance} pts>"


class RewardTransaction(db.Model):
    """One line in a customer's points passbook. points: + for EARN/ADJUST up, − for REDEEM/REVERSE."""

    __tablename__ = "reward_transactions"

    id = db.Column(db.BigInteger, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=True, index=True)  # bill that earned/used them
    return_id = db.Column(db.Integer, db.ForeignKey("sale_returns.id"), nullable=True)  # return that took them back
    txn_type = db.Column(db.Enum(RewardTxnType, name="reward_txn_type"), nullable=False)
    points = db.Column(db.Integer, nullable=False)
    balance_after = db.Column(db.Integer, nullable=False)  # balance right after this line (passbook style)
    note = db.Column(db.String(255), nullable=True)  # e.g. "Bill S01-C01-00042"
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    customer = db.relationship("Customer", back_populates="transactions")
    sale = db.relationship("Sale")
    created_by = db.relationship("User")

    __table_args__ = (db.CheckConstraint("points <> 0", name="reward_points_not_zero"),)

    def __repr__(self) -> str:
        return f"<RewardTransaction {self.txn_type.value} {self.points:+d} -> {self.balance_after}>"