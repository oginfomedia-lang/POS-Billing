"""Purchase management API routes."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.user import User
from app.schemas.common import PagedResponse
from app.schemas.purchase_schemas import (
    GoodsReceiptCreate,
    GoodsReceiptOut,
    POPaymentHistoryOut,
    POPaymentSummary,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    QuickPaymentIn,
)
from app.services import purchase_service
from app.utils.permissions import require_permission

purchase_bp = Blueprint("purchases", __name__)


def _current_user() -> User | None:
    try:
        verify_jwt_in_request()
        return db.session.get(User, int(get_jwt_identity()))
    except Exception:
        return None


@purchase_bp.get("/purchases/dashboard")
@require_permission("purchases.read")
def get_dashboard():
    stats = purchase_service.get_dashboard()
    return jsonify(stats.model_dump(mode="json")), 200


@purchase_bp.get("/purchases")
@require_permission("purchases.read")
def list_purchases():
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 25, type=int), 100)
    items, total = purchase_service.list_purchase_orders(
        page=page,
        per_page=per_page,
        status=request.args.get("status"),
        supplier_id=request.args.get("supplier_id", type=int),
        search=request.args.get("q"),
        date_from=request.args.get("date_from"),
        date_to=request.args.get("date_to"),
        payment_filter=request.args.get("payment_filter"),
    )
    invoice_map = purchase_service._get_invoice_map([po.id for po in items])
    out = [purchase_service._enrich_po(po, invoice_map.get(po.id)).model_dump(mode="json") for po in items]
    resp = PagedResponse.build(out, total, page, per_page)
    return jsonify(resp.model_dump()), 200


@purchase_bp.post("/purchases")
@require_permission("purchases.create")
def create_purchase():
    data = PurchaseOrderCreate.model_validate(request.get_json(force=True))
    po = purchase_service.create_purchase_order(data, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 201


@purchase_bp.get("/purchases/<int:po_id>")
@require_permission("purchases.read")
def get_purchase(po_id: int):
    po = purchase_service.get_purchase_order(po_id)
    invoice_map = purchase_service._get_invoice_map([po_id])
    return jsonify(purchase_service._enrich_po(po, invoice_map.get(po_id)).model_dump(mode="json")), 200


@purchase_bp.put("/purchases/<int:po_id>")
@require_permission("purchases.update")
def update_purchase(po_id: int):
    data = PurchaseOrderUpdate.model_validate(request.get_json(force=True))
    po = purchase_service.update_purchase_order(po_id, data, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/place")
@require_permission("purchases.update")
def place_order(po_id: int):
    po = purchase_service.place_order(po_id, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/submit")
@require_permission("purchases.update")
def submit_for_approval(po_id: int):
    po = purchase_service.submit_for_approval(po_id, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/approve")
@require_permission("purchases.approve")
def approve_order(po_id: int):
    po = purchase_service.approve_order(po_id, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/close")
@require_permission("purchases.update")
def close_order(po_id: int):
    po = purchase_service.close_order(po_id, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/cancel")
@require_permission("purchases.cancel")
def cancel_order(po_id: int):
    po = purchase_service.cancel_order(po_id, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/receipts")
@require_permission("purchases.receive")
def receive_goods(po_id: int):
    data = GoodsReceiptCreate.model_validate(request.get_json(force=True))
    receipt = purchase_service.receive_goods(po_id, data, _current_user())
    return jsonify(purchase_service._enrich_receipt(receipt).model_dump(mode="json")), 201


@purchase_bp.get("/purchases/<int:po_id>/receipts")
@require_permission("purchases.read")
def list_receipts(po_id: int):
    receipts = purchase_service.get_receipts(po_id)
    out = [purchase_service._enrich_receipt(r).model_dump(mode="json") for r in receipts]
    return jsonify(out), 200


@purchase_bp.get("/purchases/<int:po_id>/payment-summary")
@require_permission("purchases.read")
def get_payment_summary(po_id: int):
    summary = purchase_service.get_payment_summary(po_id)
    return jsonify(summary.model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/quick-payment")
@require_permission("payments.create")
def quick_payment(po_id: int):
    data = QuickPaymentIn.model_validate(request.get_json(force=True))
    summary = purchase_service.quick_payment(po_id, data, _current_user())
    return jsonify(summary.model_dump(mode="json")), 201


@purchase_bp.get("/purchases/<int:po_id>/payment-history")
@require_permission("purchases.read")
def get_payment_history(po_id: int):
    history = purchase_service.get_payment_history(po_id)
    return jsonify(history.model_dump(mode="json")), 200
