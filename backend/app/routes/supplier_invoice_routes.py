"""Supplier invoice API routes."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.user import User
from app.schemas.common import PagedResponse
from app.schemas.supplier_invoice_schemas import SupplierInvoiceCreate, SupplierInvoiceUpdate
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
    data = SupplierInvoiceCreate.model_validate(request.get_json(force=True))
    inv = svc.create_invoice(data, _current_user())
    return jsonify(inv.model_dump(mode="json")), 201


@supplier_invoice_bp.get("/supplier-invoices/<int:invoice_id>")
@require_permission("invoices.read")
def get_invoice(invoice_id: int):
    inv = svc.get_invoice(invoice_id)
    from app.schemas.supplier_invoice_schemas import SupplierInvoiceOut
    from decimal import Decimal
    out = SupplierInvoiceOut.model_validate(inv)
    if inv.supplier:
        out.supplier_name = inv.supplier.company_name
    if inv.purchase_order:
        out.po_number = inv.purchase_order.po_number
    out.grn_ids = [g.goods_receipt_id for g in inv.grn_links]
    out.outstanding = Decimal(str(inv.grand_total)) - Decimal(str(inv.amount_paid))
    return jsonify(out.model_dump(mode="json")), 200


@supplier_invoice_bp.put("/supplier-invoices/<int:invoice_id>")
@require_permission("invoices.update")
def update_invoice(invoice_id: int):
    data = SupplierInvoiceUpdate.model_validate(request.get_json(force=True))
    inv = svc.update_invoice(invoice_id, data, _current_user())
    return jsonify(inv.model_dump(mode="json")), 200
