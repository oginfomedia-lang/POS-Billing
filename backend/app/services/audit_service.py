"""log(user, action, entity_type, entity_id, old_values, new_values)."""
from __future__ import annotations

from flask import has_request_context, request

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.user import User


def log(
    user: User | None,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        old_values=old_values,
        new_values=new_values,
        ip_address=request.remote_addr if has_request_context() else None,
    )
    db.session.add(entry)
    return entry
