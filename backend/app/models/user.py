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

    store = db.relationship("Store", back_populates="users")
    audit_logs = db.relationship("AuditLog", back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.username} ({self.role.value})>"
