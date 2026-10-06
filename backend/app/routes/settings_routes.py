"""System settings and backup status endpoints."""
from flask import Blueprint, jsonify, request

from app.schemas.settings_schemas import SettingsData
from app.services import auth_service, settings_service
from app.utils.permissions import require_permission

settings_bp = Blueprint("settings", __name__)


@settings_bp.get("/settings")
@require_permission("settings.read")
def get_settings():
    return jsonify(settings_service.get_settings().model_dump(mode="json")), 200


@settings_bp.put("/settings")
@require_permission("settings.manage")
def update_settings():
    data = SettingsData.model_validate(request.get_json(force=True))
    saved = settings_service.update_settings(data, auth_service.current_user())
    return jsonify(saved.model_dump(mode="json")), 200
