"""Imports every model so Alembic can detect all tables."""
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.store import Counter, Store  # noqa: F401
from app.models.user import User  # noqa: F401
