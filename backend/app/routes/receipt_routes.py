"""GET /sales/<id>/receipt for reprint; POST /sales/<id>/ebill to send the bill on WhatsApp."""
from flask import Blueprint, jsonify, request

from app.schemas.sale_schemas import EbillSendRequest, EbillStatusOut
from app.services import auth_service, ebill_service, receipt_service
from app.utils.permissions import require_permission

receipt_bp = Blueprint("receipts", __name__)


@receipt_bp.get("/sales/<int:sale_id>/receipt")
@require_permission("sales.read")
def get_receipt(sale_id: int):
    receipt = receipt_service.build_receipt(sale_id)
    return jsonify(receipt.model_dump(mode="json")), 200


@receipt_bp.post("/sales/<int:sale_id>/ebill")
@require_permission("sales.read")
def send_ebill(sale_id: int):
    """Cashier's "Send on WhatsApp" (e.g. printer not working). Waits for WhatsApp's answer."""
    data = EbillSendRequest.model_validate(request.get_json(silent=True) or {})
    status = ebill_service.resend(sale_id, data.mobile, auth_service.current_user())
    return jsonify(EbillStatusOut(**status).model_dump(mode="json")), 200
