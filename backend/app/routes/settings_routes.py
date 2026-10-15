"""System settings and backup status endpoints."""
from flask import Blueprint, jsonify, request

from app.errors.exceptions import NotFoundError
from app.schemas.settings_schemas import IntegrationsUpdate, SettingsData
from app.services import (
    auth_service,
    daily_report_service,
    integration_settings_service,
    razorpay_gateway,
    settings_service,
    whatsapp_gateway,
)
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


@settings_bp.post("/settings/daily-report/send")
@require_permission("settings.manage")
def send_daily_report():
    """Sends today's collection summary to the configured mobiles right now (also a quick setup test)."""
    results = daily_report_service.send_now(auth_service.current_user())
    return jsonify([r.__dict__ for r in results]), 200


@settings_bp.get("/settings/daily-report/logs")
@require_permission("settings.read")
def daily_report_logs():
    return jsonify(daily_report_service.recent_logs()), 200


@settings_bp.get("/settings/integrations")
@require_permission("integrations.manage")
def get_integrations():
    """Razorpay / Paytm / WhatsApp details. Secrets are never sent back, only whether they are set."""
    return jsonify(integration_settings_service.public_view()), 200


@settings_bp.put("/settings/integrations")
@require_permission("integrations.manage")
def update_integrations():
    data = IntegrationsUpdate.model_validate(request.get_json(force=True))
    view = integration_settings_service.update(data.model_dump(exclude_unset=True), auth_service.current_user())
    return jsonify(view), 200


@settings_bp.post("/settings/integrations/test/<provider>")
@require_permission("integrations.manage")
def test_integration(provider: str):
    """Checks the saved credentials with a read-only call (no money moves, no message is sent)."""
    checks = {"razorpay": razorpay_gateway.check_credentials, "whatsapp": whatsapp_gateway.check_credentials}
    if provider not in checks:
        raise NotFoundError(f"No connection test for '{provider}'.")
    return jsonify({"message": checks[provider]()}), 200
