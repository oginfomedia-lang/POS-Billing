"""GET /sales/<id>/receipt for reprint."""
from flask import Blueprint, jsonify

from app.services import receipt_service
from app.utils.permissions import require_permission

receipt_bp = Blueprint("receipts", __name__)


@receipt_bp.get("/sales/<int:sale_id>/receipt")
@require_permission("sales.read")
def get_receipt(sale_id: int):
    receipt = receipt_service.build_receipt(sale_id)
    return jsonify(receipt.model_dump(mode="json")), 200
