"""Backup management endpoints — admin only."""
import math

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.user import User
from app.services import audit_service, backup_service
from app.utils.permissions import require_permission

backup_bp = Blueprint("backup", __name__)


def _current_user() -> User:
    verify_jwt_in_request()
    user_id = get_jwt_identity()
    return db.session.get(User, int(user_id))


def _serialize(r) -> dict:
    return {
        "id": r.id,
        "filename": r.filename,
        "file_size_bytes": r.file_size_bytes,
        "checksum_sha256": r.checksum_sha256,
        "status": r.status,
        "storage_location": r.storage_location,
        "cloud_path": r.cloud_path,
        "verified": r.verified,
        "verified_at": r.verified_at.isoformat() if r.verified_at else None,
        "restore_tested": r.restore_tested,
        "restore_tested_at": r.restore_tested_at.isoformat() if r.restore_tested_at else None,
        "download_count": r.download_count,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "error_message": r.error_message,
        "created_by_id": r.created_by_id,
    }


@backup_bp.get("/backups")
@require_permission("backup.read")
def list_backups():
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(int(request.args.get("per_page", 20)), 50)
    items, total = backup_service.list_backups(page=page, per_page=per_page)
    pages = math.ceil(total / per_page) if per_page else 1
    return jsonify({
        "items": [_serialize(r) for r in items],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }), 200


@backup_bp.post("/backups")
@require_permission("backup.manage")
def create_backup():
    user = _current_user()
    run = backup_service.create_backup(user)
    return jsonify(_serialize(run)), 201


@backup_bp.get("/backups/<int:backup_id>/download")
@require_permission("backup.read")
def download_backup(backup_id: int):
    user = _current_user()
    path, run = backup_service.get_download_path(backup_id)
    run.download_count += 1
    audit_service.log(user, "backup.download", "backup", run.id, new_values={"filename": run.filename})
    db.session.commit()
    return send_file(
        path,
        as_attachment=True,
        download_name=run.filename,
        mimetype="application/octet-stream",
    )


@backup_bp.post("/backups/<int:backup_id>/verify")
@require_permission("backup.manage")
def verify_backup(backup_id: int):
    user = _current_user()
    run = backup_service.verify_backup(backup_id, user)
    return jsonify(_serialize(run)), 200


@backup_bp.delete("/backups/<int:backup_id>")
@require_permission("backup.manage")
def delete_backup(backup_id: int):
    user = _current_user()
    run = backup_service.delete_backup(backup_id, user)
    return jsonify({"id": run.id, "status": run.status}), 200
