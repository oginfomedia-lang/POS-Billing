"""Supplier management API routes."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import db
from app.models.user import User
from app.schemas.common import PagedResponse, PaginationQuery
from app.schemas.supplier_schemas import (
    SupplierCreate,
    SupplierOut,
    SupplierProductCreate,
    SupplierProductUpdate,
    SupplierUpdate,
)
from app.services import purchase_service, supplier_service
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


@supplier_bp.get("/suppliers/<int:supplier_id>/summary")
@require_permission("suppliers.read")
def get_supplier_summary(supplier_id: int):
    summary = supplier_service.get_supplier_summary(supplier_id)
    return jsonify(summary.model_dump()), 200


@supplier_bp.get("/suppliers/<int:supplier_id>/ledger")
@require_permission("suppliers.read")
def get_supplier_ledger(supplier_id: int):
    entries = supplier_service.get_supplier_ledger(
        supplier_id,
        date_from=request.args.get("date_from"),
        date_to=request.args.get("date_to"),
    )
    return jsonify([e.model_dump() for e in entries]), 200


@supplier_bp.get("/suppliers/<int:supplier_id>/grns")
@require_permission("purchases.read")
def list_supplier_grns(supplier_id: int):
    """Goods received from this supplier, with value and invoice. ?uninvoiced=1 = not billed yet."""
    supplier_service.get_supplier(supplier_id)
    uninvoiced = request.args.get("uninvoiced", "0").lower() in ("1", "true")
    grns = purchase_service.supplier_grns(supplier_id, uninvoiced_only=uninvoiced)
    return jsonify([g.model_dump(mode="json") for g in grns]), 200


# ── Supplier-product mapping ──────────────────────────────────────────────────

@supplier_bp.get("/suppliers/<int:supplier_id>/products")
@require_permission("suppliers.read")
def list_supplier_products(supplier_id: int):
    items = supplier_service.get_supplier_products(supplier_id)
    return jsonify([i.model_dump(mode="json") for i in items]), 200


@supplier_bp.get("/suppliers/<int:supplier_id>/po-products")
@require_permission("purchases.read")
def supplier_po_products(supplier_id: int):
    return jsonify(supplier_service.get_products_for_po(supplier_id)), 200


@supplier_bp.post("/suppliers/<int:supplier_id>/products")
@require_permission("suppliers.update")
def add_supplier_product(supplier_id: int):
    data = SupplierProductCreate.model_validate(request.get_json(force=True))
    item = supplier_service.add_supplier_product(supplier_id, data, _current_user())
    return jsonify(item.model_dump(mode="json")), 201


@supplier_bp.put("/suppliers/<int:supplier_id>/products/<int:sp_id>")
@require_permission("suppliers.update")
def update_supplier_product(supplier_id: int, sp_id: int):
    data = SupplierProductUpdate.model_validate(request.get_json(force=True))
    item = supplier_service.update_supplier_product(supplier_id, sp_id, data, _current_user())
    return jsonify(item.model_dump(mode="json")), 200


@supplier_bp.delete("/suppliers/<int:supplier_id>/products/<int:sp_id>")
@require_permission("suppliers.update")
def remove_supplier_product(supplier_id: int, sp_id: int):
    supplier_service.remove_supplier_product(supplier_id, sp_id, _current_user())
    return jsonify({"message": "Removed."}), 200
