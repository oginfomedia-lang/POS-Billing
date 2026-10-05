"""AuditLog model (who changed what, old/new values as JSONB)."""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(50), nullable=True)   # denormalized: survives user deletion
    action = Column(String(100), nullable=False)   # e.g. "user.create"
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(50), nullable=True)
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    user = relationship("User", back_populates="audit_logs")
