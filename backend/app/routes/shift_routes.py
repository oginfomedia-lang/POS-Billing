"""Open / active / close shift endpoints."""
from flask import Blueprint, jsonify, request

from app.schemas.shift_schemas import CloseShiftRequest, OpenShiftRequest, ShiftOut
from app.services import auth_service, shift_service
from app.utils.permissions import require_permission

shift_bp = Blueprint("shifts", __name__)


@shift_bp.post("/shifts/open")
@require_permission("shifts.manage")
def open_shift():
    data = OpenShiftRequest.model_validate(request.get_json(force=True))
    user = auth_service.current_user()
    shift = shift_service.open_shift(user, data)
    return jsonify(ShiftOut.model_validate(shift).model_dump(mode="json")), 201


@shift_bp.get("/shifts/active")
@require_permission("shifts.read")
def get_active_shift():
    user = auth_service.current_user()
    shift = shift_service.get_active_shift(user.id)
    return jsonify(ShiftOut.model_validate(shift).model_dump(mode="json")), 200


@shift_bp.post("/shifts/<int:shift_id>/close")
@require_permission("shifts.manage")
def close_shift(shift_id: int):
    data = CloseShiftRequest.model_validate(request.get_json(force=True))
    user = auth_service.current_user()
    shift = shift_service.close_shift(shift_id, user.id, data)
    return jsonify(ShiftOut.model_validate(shift).model_dump(mode="json")), 200


@shift_bp.get("/shifts/<int:shift_id>/bills")
@require_permission("shifts.read")
def shift_bills(shift_id: int):
    """Bills, refunds and expected cash for one shift (the cashier's own, or any for admin / manager)."""
    out = shift_service.shift_bills(shift_id, auth_service.current_user())
    return jsonify(out.model_dump(mode="json")), 200
