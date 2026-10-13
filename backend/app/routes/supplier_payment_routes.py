"""Supplier payment API routes."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.user import User
from app.schemas.common import PagedResponse
from app.schemas.supplier_payment_schemas import SupplierPaymentCreate
from app.services import supplier_payment_service as svc
from app.utils.permissions import require_permission

supplier_payment_bp = Blueprint("supplier_payments", __name__)


def _current_user() -> User | None:
    try:
        verify_jwt_in_request()
        return db.session.get(User, int(get_jwt_identity()))
    except Exception:
        return None


@supplier_payment_bp.get("/supplier-payments")
@require_permission("payments.read")
def list_payments():
    items, total = svc.list_payments(
        supplier_id=request.args.get("supplier_id", type=int),
        page=request.args.get("page", 1, type=int),
        per_page=min(request.args.get("per_page", 25, type=int), 100),
    )
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 25, type=int), 100)
    resp = PagedResponse.build([i.model_dump(mode="json") for i in items], total, page, per_page)
    return jsonify(resp.model_dump()), 200


@supplier_payment_bp.post("/supplier-payments")
@require_permission("payments.create")
def create_payment():
    data = SupplierPaymentCreate.model_validate(request.get_json(force=True))
    pay = svc.create_payment(data, _current_user())
    return jsonify(pay.model_dump(mode="json")), 201


@supplier_payment_bp.get("/supplier-payments/<int:payment_id>")
@require_permission("payments.read")
def get_payment(payment_id: int):
    pay = svc.get_payment(payment_id)
    out = svc._enrich(pay)
    return jsonify(out.model_dump(mode="json")), 200


@supplier_payment_bp.post("/supplier-payments/<int:payment_id>/void")
@require_permission("payments.void")
def void_payment(payment_id: int):
    pay = svc.void_payment(payment_id, _current_user())
    return jsonify(pay.model_dump(mode="json")), 200
