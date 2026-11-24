"""Customers and reward points: balance lookup at the counter, list and passbook for admins."""
from flask import Blueprint, jsonify, request

from app.schemas.common import PagedResponse
from app.schemas.customer_schemas import (
    CreditLimitUpdateRequest,
    CreditRepaymentRequest,
    CreditTxnOut,
    CustomerCreditInfoOut,
    CustomerNameUpdateRequest,
    CustomerOut,
    RewardTxnOut,
)
from app.errors.exceptions import ValidationError
from app.services import auth_service, customer_credit_service, loyalty_service
from app.utils.permissions import require_permission
from app.utils.store_scope import is_head_office, require_store_access

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
    with_dues = request.args.get("with_dues", "false").lower() in ("true", "1", "yes")
    items, total = loyalty_service.list_customers(request.args.get("search"), page, per_page, with_dues=with_dues)
    out = PagedResponse.build([CustomerOut.model_validate(c) for c in items], total, page, per_page)
    return jsonify(out.model_dump(mode="json")), 200


@customer_bp.get("/customers/<int:customer_id>/transactions")
@require_permission("reports.read")
def customer_transactions(customer_id: int):
    page, per_page = _paging(50)
    items, total = loyalty_service.customer_ledger(customer_id, page, per_page)
    out = PagedResponse.build([RewardTxnOut.model_validate(t) for t in items], total, page, per_page)
    return jsonify(out.model_dump(mode="json")), 200

@customer_bp.get("/customers/<mobile>/credit")
@require_permission("sales.create")
def get_credit(mobile: str):
    """POS checks customer credit balance & limit when typing phone number."""
    return jsonify(customer_credit_service.get_credit_info(mobile).model_dump(mode="json")), 200


@customer_bp.post("/customers/<int:customer_id>/repay")
@require_permission("sales.create")
def repay_credit(customer_id: int):
    """Record customer repayment towards their Udhari."""
    data = CreditRepaymentRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    # Staff repay at their own store; head office (no fixed store) must say which store took the money.
    store_id = data.store_id if is_head_office(actor) and data.store_id is not None else actor.store_id
    if store_id is None:
        raise ValidationError("Choose the store that received this payment.")
    require_store_access(actor, store_id)
    txn = customer_credit_service.record_repayment(
        customer_id=customer_id,
        store_id=store_id,
        amount=data.amount,
        payment_method=data.payment_method,
        reference=data.reference,
        note=data.note,
        actor=actor,
    )
    return jsonify(CreditTxnOut.model_validate(txn).model_dump(mode="json")), 201


@customer_bp.put("/customers/<int:customer_id>/name")
@require_permission("sales.create")
def set_name(customer_id: int):
    """Staff add or correct a customer's name."""
    data = CustomerNameUpdateRequest.model_validate(request.get_json(force=True))
    customer = customer_credit_service.update_name(customer_id, data.name, auth_service.current_user())
    return jsonify(CustomerOut.model_validate(customer).model_dump(mode="json")), 200


@customer_bp.put("/customers/<int:customer_id>/credit-limit")
@require_permission("settings.manage")
def set_credit_limit(customer_id: int):
    """Admin updates customer credit limit."""
    data = CreditLimitUpdateRequest.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    customer = customer_credit_service.update_credit_limit(customer_id, data.credit_limit, actor)
    return jsonify(CustomerOut.model_validate(customer).model_dump(mode="json")), 200


@customer_bp.get("/customers/<int:customer_id>/credit-transactions")
@require_permission("reports.read")
def customer_credit_transactions(customer_id: int):
    """Get customer's Khata passbook statement."""
    page, per_page = _paging(50)
    items, total = customer_credit_service.customer_credit_ledger(customer_id, page, per_page)
    out = PagedResponse.build([CreditTxnOut.model_validate(t) for t in items], total, page, per_page)
    return jsonify(out.model_dump(mode="json")), 200