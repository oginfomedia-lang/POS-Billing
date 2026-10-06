"""Open / active / close shift endpoints."""
from flask import Blueprint, jsonify, request

from app.errors.exceptions import NotFoundError
from app.schemas.shift_schemas import OpenShiftRequest, ShiftOut
from app.services import auth_service, shift_service
from app.utils.permissions import require_permission

shift_bp = Blueprint("shifts", __name__)


@shift_bp.post("/shifts/open")
@require_permission("shifts.open")
def open_shift():
    data = OpenShiftRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    shift = shift_service.open_shift(data, actor)
    return jsonify(ShiftOut.model_validate(shift).model_dump(mode="json")), 201


@shift_bp.get("/shifts/active")
@require_permission("shifts.read")
def active_shift():
    actor = auth_service.current_user()
    shift = shift_service.get_active_shift(actor)
    if shift is None:
        raise NotFoundError("No open shift.")
    return jsonify(ShiftOut.model_validate(shift).model_dump(mode="json")), 200
