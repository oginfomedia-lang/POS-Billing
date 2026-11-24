"""Review selling prices: the list, Apply (set the price) and Keep as is. Admins and managers (they see costs)."""
from flask import Blueprint, jsonify, request

from app.errors.exceptions import PermissionDeniedError, ValidationError
from app.schemas.price_review_schemas import ApplyPriceRequest
from app.services import auth_service, price_review_service
from app.utils.permissions import has_permission, require_permission

price_review_bp = Blueprint("price_review", __name__)


def _actor_who_may_change():
    actor = auth_service.current_user()
    if not has_permission(actor.role, "products.update"):
        raise PermissionDeniedError("You can't change selling prices.")
    return actor


@price_review_bp.get("/price-review")
@require_permission("products.cost")
def review_list():
    """?product_ids=1,2,3 for only those (e.g. the products of one goods receipt)."""
    raw = request.args.get("product_ids", "").strip()
    try:
        ids = [int(x) for x in raw.split(",") if x.strip()] if raw else None
    except ValueError:
        raise ValidationError("product_ids must be numbers separated by commas.") from None
    out = price_review_service.review_list(auth_service.current_user(), ids)
    return jsonify(out.model_dump(mode="json")), 200


@price_review_bp.post("/price-review/<int:product_id>/apply")
@require_permission("products.cost")
def apply_price(product_id: int):
    data = ApplyPriceRequest.model_validate(request.get_json(force=True))
    row = price_review_service.apply_price(product_id, data.price, _actor_who_may_change())
    return jsonify(row.model_dump(mode="json")), 200


@price_review_bp.post("/price-review/<int:product_id>/keep")
@require_permission("products.cost")
def keep_price(product_id: int):
    price_review_service.keep_price(product_id, _actor_who_may_change())
    return jsonify({"product_id": product_id, "kept": True}), 200
