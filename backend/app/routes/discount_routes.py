"""Discount endpoints (admin / manager)."""
from flask import Blueprint, jsonify, request

from app.schemas.discount_schemas import DiscountIn, DiscountOut
from app.services import auth_service, discount_service
from app.utils.permissions import require_permission
from app.utils.store_scope import scoped_store_id

discount_bp = Blueprint("discounts", __name__)


@discount_bp.get("/discounts")
@require_permission("discounts.read")
def list_discounts():
    """?store_id= shows that store's offers plus all-store offers. Branch users always get their own store."""
    store_id = scoped_store_id(auth_service.current_user(), request.args.get("store_id", type=int))
    items = discount_service.list_discounts(store_id)
    return jsonify([DiscountOut.model_validate(d).model_dump(mode="json") for d in items]), 200


@discount_bp.post("/discounts")
@require_permission("discounts.manage")
def create_discount():
    data = DiscountIn.model_validate(request.get_json(force=True))
    discount = discount_service.create_discount(data, auth_service.current_user())
    return jsonify(DiscountOut.model_validate(discount).model_dump(mode="json")), 201


@discount_bp.put("/discounts/<int:discount_id>")
@require_permission("discounts.manage")
def update_discount(discount_id: int):
    data = DiscountIn.model_validate(request.get_json(force=True))
    discount = discount_service.update_discount(discount_id, data, auth_service.current_user())
    return jsonify(DiscountOut.model_validate(discount).model_dump(mode="json")), 200
