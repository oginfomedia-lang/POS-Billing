"""GET /api/v1/license, POST /api/v1/license/activate - the shop licence, shared by every PC in the store.

No login needed: the licence screen comes before the login screen, and a key only works for this
server's machine ID, so activating from any counter is safe.
"""
from flask import Blueprint, current_app, jsonify, request

from app.errors.exceptions import ValidationError
from app.errors.handlers import error_response
from app.services import license_service

license_bp = Blueprint("license", __name__)


@license_bp.get("/license")
def get_license():
    # required=false in development: the app then skips the licence screen.
    return jsonify({**license_service.current_status().to_dict(),
                    "required": bool(current_app.config.get("LICENSE_REQUIRED"))})


@license_bp.post("/license/activate")
def activate_license():
    key = (request.get_json(silent=True) or {}).get("key")
    if not isinstance(key, str) or not key.strip():
        raise ValidationError("Enter the licence key.")
    status = license_service.activate(key)
    if not status.valid:
        # code: LICENSE_INVALID_KEY / LICENSE_WRONG_MACHINE / LICENSE_EXPIRED
        return error_response(400, f"LICENSE_{status.reason.upper()}", "The licence key was not accepted.",
                              status.to_dict())
    return jsonify(status.to_dict())
