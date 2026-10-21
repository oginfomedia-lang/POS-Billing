"""User model."""
from app.extensions import db
from app.models.base import TimestampMixin
from app.models.enums import UserRole


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(150), nullable=False)
    pin_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(UserRole, name="user_role"), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=True)
    # Goes up when an admin resets the PIN or changes role / store / active. Every token carries the value it
    # was issued with ("sv"); a token with an older value is refused, so the person is logged out everywhere.
    session_version = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # Wrong PINs in a row (login or manager approval), and until when the account is locked after too many.
    pin_failures = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    pin_locked_until = db.Column(db.DateTime(timezone=True), nullable=True)

    store = db.relationship("Store", back_populates="users")
    audit_logs = db.relationship("AuditLog", back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role.value})>"
