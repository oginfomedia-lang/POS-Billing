"""Purchase management API routes."""
import io
import json

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.errors.exceptions import BadRequestError, PermissionDeniedError
from app.extensions import db
from app.models.user import User
from app.schemas.common import PagedResponse
from app.schemas.purchase_schemas import (
    DirectPurchaseCreate,
    GoodsReceiptCreate,
    MarkSentRequest,
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
)
from app.services import bill_ocr_service, direct_purchase_service, po_pdf, po_sending_service, purchase_service
from app.utils.permissions import has_permission, require_permission
from app.utils.store_scope import require_store_access

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
    money = purchase_service._po_money_map([po.id for po in items])
    out = [purchase_service._enrich_po(po, money[po.id]).model_dump(mode="json") for po in items]
    resp = PagedResponse.build(out, total, page, per_page)
    return jsonify(resp.model_dump()), 200


@purchase_bp.post("/purchases")
@require_permission("purchases.create")
def create_purchase():
    data = PurchaseOrderCreate.model_validate(request.get_json(force=True))
    po = purchase_service.create_purchase_order(data, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 201


@purchase_bp.post("/purchases/direct")
@require_permission("purchases.receive")
def create_direct_purchase():
    """Goods arrived without a PO. multipart/form-data: 'data' = the bill as JSON, 'file' = the bill (required)."""
    actor = _current_user()
    if not has_permission(actor.role, "invoices.create"):
        raise PermissionDeniedError("You can't enter supplier invoices.")
    try:
        payload = json.loads(request.form.get("data") or "{}")
    except ValueError:
        raise BadRequestError("Invalid purchase data.") from None
    data = DirectPurchaseCreate.model_validate(payload)
    require_store_access(actor, data.store_id)
    po, invoice = direct_purchase_service.create_direct_purchase(data, bill_ocr_service.one_bill_file(request.files.getlist("file")), actor)
    return jsonify({
        "purchase_order": purchase_service._enrich_po(po).model_dump(mode="json"),
        "invoice": invoice.model_dump(mode="json"),
    }), 201


@purchase_bp.post("/purchases/direct/extract")
@require_permission("purchases.receive")
def extract_direct_purchase_bill():
    """Reads the supplier's bill and returns a draft to check. Saves nothing.
    multipart/form-data: 'file' = the bill (PDF or photo), 'store_id', 'supplier_id' (optional: found from the GSTIN)."""
    actor = _current_user()
    store_id = request.form.get("store_id", type=int)
    if not store_id:
        raise BadRequestError("Choose the store first.")
    require_store_access(actor, store_id)
    draft = bill_ocr_service.extract_bill(
        request.files.getlist("file"), store_id, request.form.get("supplier_id", type=int)
    )
    return jsonify(draft.model_dump(mode="json")), 200


@purchase_bp.get("/purchases/<int:po_id>/direct")
@require_permission("purchases.receive")
def get_direct_purchase(po_id: int):
    """A saved direct purchase, to correct it in the same form."""
    draft = direct_purchase_service.get_for_edit(po_id)
    require_store_access(_current_user(), draft.store_id)
    return jsonify(draft.model_dump(mode="json")), 200


@purchase_bp.put("/purchases/<int:po_id>/direct")
@require_permission("purchases.receive")
def update_direct_purchase(po_id: int):
    """Corrects a saved direct purchase. Same form data as POST /purchases/direct; no 'file' = keep the saved bill."""
    actor = _current_user()
    if not has_permission(actor.role, "invoices.create"):
        raise PermissionDeniedError("You can't enter supplier invoices.")
    try:
        payload = json.loads(request.form.get("data") or "{}")
    except ValueError:
        raise BadRequestError("Invalid purchase data.") from None
    data = DirectPurchaseCreate.model_validate(payload)
    require_store_access(actor, purchase_service.get_purchase_order(po_id).store_id)
    require_store_access(actor, data.store_id)
    po, invoice = direct_purchase_service.update_direct_purchase(
        po_id, data, bill_ocr_service.one_bill_file(request.files.getlist("file")), actor)
    return jsonify({
        "purchase_order": purchase_service._enrich_po(po).model_dump(mode="json"),
        "invoice": invoice.model_dump(mode="json"),
    }), 200


@purchase_bp.get("/purchases/<int:po_id>")
@require_permission("purchases.read")
def get_purchase(po_id: int):
    po = purchase_service.get_purchase_order(po_id)
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 200


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


@purchase_bp.get("/purchases/<int:po_id>/pdf")
@require_permission("purchases.read")
def purchase_pdf(po_id: int):
    po = purchase_service.get_purchase_order(po_id)
    return send_file(
        io.BytesIO(po_pdf.render(po)),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=po_pdf.filename(po),
    )


@purchase_bp.get("/purchases/<int:po_id>/supplier-message")
@require_permission("purchases.read")
def supplier_message(po_id: int):
    return jsonify(po_sending_service.supplier_message(po_id).model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/email")
@require_permission("purchases.update")
def email_purchase(po_id: int):
    po = po_sending_service.send_email_now(po_id, _current_user())
    return jsonify(purchase_service._enrich_po(po).model_dump(mode="json")), 200


@purchase_bp.post("/purchases/<int:po_id>/mark-sent")
@require_permission("purchases.update")
def mark_sent(po_id: int):
    data = MarkSentRequest.model_validate(request.get_json(force=True))
    po = po_sending_service.mark_sent(po_id, data.via, _current_user())
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


@purchase_bp.get("/purchases/<int:po_id>/payment-history")
@require_permission("purchases.read")
def get_payment_history(po_id: int):
    history = purchase_service.get_payment_history(po_id)
    return jsonify(history.model_dump(mode="json")), 200
