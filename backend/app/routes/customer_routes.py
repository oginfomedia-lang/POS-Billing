"""Customers and reward points: balance lookup at the counter, list and passbook for admins."""
from flask import Blueprint, jsonify, request

from app.schemas.common import PagedResponse
from app.schemas.customer_schemas import CustomerOut, RewardTxnOut
from app.services import loyalty_service
from app.utils.permissions import require_permission

customer_bp = Blueprint("customers", __name__)


def _paging(default: int) -> tuple[int, int]:
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", default, type=int), 1), 100)
    return page, per_page


@customer_bp.get("/customers/<mobile>/rewards")
@require_permission("sales.create")
def rewards(mobile: str):
    return jsonify(loyalty_service.rewards_for_mobile(mobile).model_dump(mode="json")), 200


@customer_bp.get("/customers")
@require_permission("reports.read")
def list_customers():
    page, per_page = _paging(25)
    items, total = loyalty_service.list_customers(request.args.get("search"), page, per_page)
    out = PagedResponse.build([CustomerOut.model_validate(c) for c in items], total, page, per_page)
    return jsonify(out.model_dump(mode="json")), 200


@customer_bp.get("/customers/<int:customer_id>/transactions")
@require_permission("reports.read")
def customer_transactions(customer_id: int):
    page, per_page = _paging(50)
    items, total = loyalty_service.customer_ledger(customer_id, page, per_page)
    out = PagedResponse.build([RewardTxnOut.model_validate(t) for t in items], total, page, per_page)
    return jsonify(out.model_dump(mode="json")), 200
