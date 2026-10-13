"""Supplier invoice API routes."""
import json

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.errors.exceptions import BadRequestError
from app.extensions import db
from app.models.user import User
from app.schemas.common import PagedResponse
from app.schemas.supplier_invoice_schemas import SupplierInvoiceCancelIn, SupplierInvoiceCreate, SupplierInvoiceUpdate
from app.services import supplier_invoice_service as svc
from app.utils.permissions import require_permission

supplier_invoice_bp = Blueprint("supplier_invoices", __name__)


def _current_user() -> User | None:
    try:
        verify_jwt_in_request()
        return db.session.get(User, int(get_jwt_identity()))
    except Exception:
        return None


@supplier_invoice_bp.get("/supplier-invoices")
@require_permission("invoices.read")
def list_invoices():
    items, total = svc.list_invoices(
        supplier_id=request.args.get("supplier_id", type=int),
        payment_status=request.args.get("payment_status"),
        date_from=request.args.get("date_from"),
        date_to=request.args.get("date_to"),
        page=request.args.get("page", 1, type=int),
        per_page=min(request.args.get("per_page", 25, type=int), 100),
    )
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 25, type=int), 100)
    resp = PagedResponse.build([i.model_dump(mode="json") for i in items], total, page, per_page)
    return jsonify(resp.model_dump()), 200


@supplier_invoice_bp.post("/supplier-invoices")
@require_permission("invoices.create")
def create_invoice():
    """multipart/form-data: 'data' = the invoice as JSON, 'file' = the supplier's bill (PDF/photo, required)."""
    try:
        payload = json.loads(request.form.get("data") or "{}")
    except ValueError:
        raise BadRequestError("Invalid invoice data.") from None
    data = SupplierInvoiceCreate.model_validate(payload)
    inv = svc.create_invoice(data, request.files.get("file"), _current_user())
    return jsonify(inv.model_dump(mode="json")), 201


@supplier_invoice_bp.get("/supplier-invoices/preview-grns")
@require_permission("invoices.read")
def preview_grns():
    """?supplier_id=1&grn_ids=4,5 → the value of those goods, for the add-invoice form."""
    supplier_id = request.args.get("supplier_id", type=int)
    raw = request.args.get("grn_ids", "")
    try:
        grn_ids = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        raise BadRequestError("grn_ids must be numbers.") from None
    if not supplier_id:
        raise BadRequestError("supplier_id is required.")
    return jsonify(svc.preview_grns(supplier_id, grn_ids).model_dump(mode="json")), 200


@supplier_invoice_bp.get("/supplier-invoices/<int:invoice_id>")
@require_permission("invoices.read")
def get_invoice(invoice_id: int):
    return jsonify(svc.enrich(svc.get_invoice(invoice_id)).model_dump(mode="json")), 200


@supplier_invoice_bp.put("/supplier-invoices/<int:invoice_id>")
@require_permission("invoices.update")
def update_invoice(invoice_id: int):
    data = SupplierInvoiceUpdate.model_validate(request.get_json(force=True))
    inv = svc.update_invoice(invoice_id, data, _current_user())
    return jsonify(inv.model_dump(mode="json")), 200


@supplier_invoice_bp.post("/supplier-invoices/<int:invoice_id>/cancel")
@require_permission("invoices.update")
def cancel_invoice(invoice_id: int):
    """Wrong / duplicate bill: cancel it (nothing paid on it) so its GRNs can be billed again."""
    data = SupplierInvoiceCancelIn.model_validate(request.get_json(force=True))
    inv = svc.cancel_invoice(invoice_id, data.reason, _current_user())
    return jsonify(inv.model_dump(mode="json")), 200
