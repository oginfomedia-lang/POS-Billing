"""NotificationLog: one outgoing WhatsApp message.

- Nightly collection summary: one per day/store/recipient (sale_id is NULL).
- E-bill: one per bill/recipient (sale_id set).
"""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import NotificationStatus


class NotificationLog(TimestampMixin, db.Model):
    __tablename__ = "notification_logs"

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(30), nullable=False)  # "daily_collection", "ebill"
    report_date = db.Column(db.Date, nullable=False)  # the IST business day the message is about
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey("sales.id"), nullable=True, index=True)  # e-bills only
    recipient = db.Column(db.String(15), nullable=False)  # 10-digit Indian mobile
    status = db.Column(
        db.Enum(NotificationStatus, name="notification_status"), nullable=False, default=NotificationStatus.PENDING
    )
    attempts = db.Column(db.Integer, nullable=False, default=0)
    provider_message_id = db.Column(db.String(100), nullable=True)  # WhatsApp "wamid..."
    error = db.Column(db.Text, nullable=True)  # last failure, shown on the settings screen
    body = db.Column(db.Text, nullable=True)  # readable copy of what was sent
    sent_at = db.Column(db.DateTime(timezone=True), nullable=True)

    store = db.relationship("Store")

    # The same day's report never goes to the same number twice; the same bill neither.
    __table_args__ = (
        db.Index(
            "uq_notification_once", "kind", "report_date", "store_id", "recipient",
            unique=True, postgresql_where=sale_id.is_(None),
        ),
        db.Index("uq_notification_ebill", "sale_id", "recipient", unique=True, postgresql_where=sale_id.isnot(None)),
    )

    def __repr__(self) -> str:
        return f"<NotificationLog {self.kind} {self.report_date} -> {self.recipient} ({self.status.value})>"
