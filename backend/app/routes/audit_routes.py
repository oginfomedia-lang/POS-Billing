"""Audit log viewer endpoints (admin only)."""
from datetime import datetime

from flask import Blueprint, jsonify, request

from app.repositories.audit_repository import AuditRepository
from app.schemas.common import PagedResponse
from app.utils.permissions import require_permission

audit_bp = Blueprint("audit", __name__)


@audit_bp.get("/audit-logs")
@require_permission("audit.read")
def list_audit_logs():
    page = int(request.args.get("page", 1))
    per_page = min(int(request.args.get("per_page", 50)), 100)
    user_id = request.args.get("user_id", type=int)
    entity_type = request.args.get("entity_type")
    action = request.args.get("action")
    user = request.args.get("user")  # role, or part of a username / full name

    repo = AuditRepository()
    items, total = repo.list(
        page=page,
        per_page=per_page,
        user_id=user_id,
        entity_type=entity_type or None,
        action=action,
        user=user,
    )

    def _serialize(log):
        return {
            "id": log.id,
            "user_id": log.user_id,
            "username": log.username,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }

    resp = PagedResponse.build([_serialize(l) for l in items], total, page, per_page)
    return jsonify(resp.model_dump()), 200


@audit_bp.get("/audit-logs/filters")
@require_permission("audit.read")
def audit_filter_values():
    """Suggestions for the filter boxes: actions, record types, roles and people found in the log."""
    return jsonify(AuditRepository().filter_values()), 200
