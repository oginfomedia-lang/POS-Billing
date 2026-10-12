"""Supplier management API routes."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.user import User
from app.schemas.common import PagedResponse, PaginationQuery
from app.schemas.supplier_schemas import SupplierCreate, SupplierOut, SupplierUpdate
from app.services import supplier_service
from app.utils.permissions import require_permission

supplier_bp = Blueprint("suppliers", __name__)


def _current_user() -> User | None:
    try:
        verify_jwt_in_request()
        return db.session.get(User, int(get_jwt_identity()))
    except Exception:
        return None


@supplier_bp.get("/suppliers/dashboard")
@require_permission("suppliers.read")
def get_dashboard():
    stats = supplier_service.get_dashboard()
    return jsonify(stats.model_dump()), 200


@supplier_bp.get("/suppliers")
@require_permission("suppliers.read")
def list_suppliers():
    q = PaginationQuery.model_validate(request.args)
    items, total, counts = supplier_service.list_suppliers(
        page=q.page,
        per_page=q.per_page,
        is_active=q.is_active,
        search=request.args.get("q"),
    )
    out = []
    for s in items:
        item = SupplierOut.model_validate(s)
        item.product_count = counts.get(s.id, 0)
        out.append(item.model_dump(mode="json"))
    resp = PagedResponse.build(out, total, q.page, q.per_page)
    return jsonify(resp.model_dump()), 200


@supplier_bp.post("/suppliers")
@require_permission("suppliers.create")
def create_supplier():
    data = SupplierCreate.model_validate(request.get_json(force=True))
    supplier = supplier_service.create_supplier(data, _current_user())
    item = SupplierOut.model_validate(supplier)
    item.product_count = 0
    return jsonify(item.model_dump(mode="json")), 201


@supplier_bp.get("/suppliers/<int:supplier_id>")
@require_permission("suppliers.read")
def get_supplier(supplier_id: int):
    supplier = supplier_service.get_supplier(supplier_id)
    counts = supplier_service.product_counts([supplier.id])
    item = SupplierOut.model_validate(supplier)
    item.product_count = counts.get(supplier.id, 0)
    return jsonify(item.model_dump(mode="json")), 200


@supplier_bp.put("/suppliers/<int:supplier_id>")
@require_permission("suppliers.update")
def update_supplier(supplier_id: int):
    data = SupplierUpdate.model_validate(request.get_json(force=True))
    supplier = supplier_service.update_supplier(supplier_id, data, _current_user())
    counts = supplier_service.product_counts([supplier.id])
    item = SupplierOut.model_validate(supplier)
    item.product_count = counts.get(supplier.id, 0)
    return jsonify(item.model_dump(mode="json")), 200


@supplier_bp.patch("/suppliers/<int:supplier_id>/status")
@require_permission("suppliers.update")
def toggle_supplier_status(supplier_id: int):
    supplier = supplier_service.get_supplier(supplier_id)
    data = SupplierUpdate(is_active=not supplier.is_active)
    supplier = supplier_service.update_supplier(supplier_id, data, _current_user())
    item = SupplierOut.model_validate(supplier)
    return jsonify(item.model_dump(mode="json")), 200
