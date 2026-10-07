"""Sales: create draft, add/update/remove items, hold, resume, void, complete."""
from flask import Blueprint, jsonify, request

from app.schemas.sale_schemas import (
    AddItemRequest,
    CompleteSaleRequest,
    HoldSaleRequest,
    ManualDiscountRequest,
    SaleOut,
    UpdateItemRequest,
)
from app.services import auth_service, billing_service
from app.utils.permissions import require_permission

billing_bp = Blueprint("billing", __name__)


def _sale_json(sale):
    return SaleOut.model_validate(sale).model_dump(mode="json")


@billing_bp.post("/sales")
@require_permission("sales.create")
def create_sale():
    actor = auth_service.current_user()
    sale, created = billing_service.create_draft(actor)
    return jsonify(_sale_json(sale)), 201 if created else 200


@billing_bp.get("/sales/held")
@require_permission("sales.read")
def list_held():
    actor = auth_service.current_user()
    sales = billing_service.list_held(actor)
    return jsonify([_sale_json(s) for s in sales]), 200


@billing_bp.post("/sales/<int:sale_id>/items")
@require_permission("sales.create")
def add_item(sale_id: int):
    data = AddItemRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    sale = billing_service.add_item(sale_id, data, actor)
    return jsonify(_sale_json(sale)), 200


@billing_bp.put("/sales/<int:sale_id>/items/<int:item_id>")
@require_permission("sales.create")
def update_item(sale_id: int, item_id: int):
    data = UpdateItemRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    sale = billing_service.update_item(sale_id, item_id, data, actor)
    return jsonify(_sale_json(sale)), 200


@billing_bp.delete("/sales/<int:sale_id>/items/<int:item_id>")
@require_permission("sales.create")
def remove_item(sale_id: int, item_id: int):
    actor = auth_service.current_user()
    sale = billing_service.remove_item(sale_id, item_id, actor)
    return jsonify(_sale_json(sale)), 200


@billing_bp.post("/sales/<int:sale_id>/items/<int:item_id>/manual-discount")
@require_permission("sales.create")
def set_manual_discount(sale_id: int, item_id: int):
    data = ManualDiscountRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    sale = billing_service.set_manual_discount(sale_id, item_id, data, actor)
    return jsonify(_sale_json(sale)), 200


@billing_bp.post("/sales/<int:sale_id>/hold")
@require_permission("sales.create")
def hold_sale(sale_id: int):
    data = HoldSaleRequest.model_validate(request.get_json(silent=True) or {})
    actor = auth_service.current_user()
    sale = billing_service.hold(sale_id, data, actor)
    return jsonify(_sale_json(sale)), 200


@billing_bp.post("/sales/<int:sale_id>/resume")
@require_permission("sales.create")
def resume_sale(sale_id: int):
    actor = auth_service.current_user()
    sale = billing_service.resume(sale_id, actor)
    return jsonify(_sale_json(sale)), 200


@billing_bp.post("/sales/<int:sale_id>/complete")
@require_permission("sales.create")
def complete_sale(sale_id: int):
    data = CompleteSaleRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    sale = billing_service.complete(sale_id, data, actor)
    return jsonify(_sale_json(sale)), 200


@billing_bp.post("/sales/<int:sale_id>/void")
@require_permission("sales.void")
def void_sale(sale_id: int):
    actor = auth_service.current_user()
    sale = billing_service.void(sale_id, actor)
    return jsonify(_sale_json(sale)), 200
