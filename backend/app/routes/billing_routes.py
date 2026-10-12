"""Sales: create draft, add/update/remove items, hold, resume, void, complete, card/UPI payments."""
from flask import Blueprint, jsonify, request

from app.schemas.customer_schemas import RedeemPointsRequest
from app.schemas.payment_schemas import PaymentIntentOut, StartPaymentRequest
from app.schemas.sale_schemas import (
    AddItemRequest,
    CompleteSaleRequest,
    CustomerMobileRequest,
    HoldSaleRequest,
    ManualDiscountRequest,
    SaleOut,
    UpdateItemRequest,
)
from app.services import auth_service, billing_service, payment_intent_service
from app.utils.permissions import require_permission

billing_bp = Blueprint("billing", __name__)


def _sale_json(sale):
    return SaleOut.model_validate(sale).model_dump(mode="json")


def _intent_json(intent):
    return PaymentIntentOut.model_validate(intent).model_dump(mode="json")


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


@billing_bp.put("/sales/<int:sale_id>/customer-mobile")
@require_permission("sales.create")
def set_customer_mobile(sale_id: int):
    data = CustomerMobileRequest.model_validate(request.get_json(force=True))
    sale = billing_service.set_customer_mobile(sale_id, data.mobile, auth_service.current_user())
    return jsonify(_sale_json(sale)), 200


@billing_bp.post("/sales/<int:sale_id>/redeem-points")
@require_permission("sales.create")
def redeem_points(sale_id: int):
    """Cashier's Redeem button: blocks of reward points off this open bill (0 removes)."""
    data = RedeemPointsRequest.model_validate(request.get_json(force=True))
    sale = billing_service.redeem_points(sale_id, data.blocks, auth_service.current_user())
    return jsonify(_sale_json(sale)), 200


@billing_bp.post("/sales/<int:sale_id>/void")
@require_permission("sales.void")
def void_sale(sale_id: int):
    actor = auth_service.current_user()
    sale = billing_service.void(sale_id, actor)
    return jsonify(_sale_json(sale)), 200


@billing_bp.post("/sales/<int:sale_id>/payment-intents")
@require_permission("sales.create")
def start_payment(sale_id: int):
    """Shows a Razorpay UPI QR for the exact total, or pushes the total to the counter's card machine."""
    data = StartPaymentRequest.model_validate(request.get_json(force=True))
    intent = payment_intent_service.start(sale_id, data.method, auth_service.current_user())
    return jsonify(_intent_json(intent)), 201


@billing_bp.get("/payment-intents/<int:intent_id>")
@require_permission("sales.create")
def check_payment(intent_id: int):
    """Polled every ~2 s. When Razorpay confirms the money the sale is completed and returned in `sale`."""
    intent, sale = payment_intent_service.check(intent_id, auth_service.current_user())
    body = _intent_json(intent)
    body["sale"] = _sale_json(sale) if sale else None
    return jsonify(body), 200


@billing_bp.post("/payment-intents/<int:intent_id>/cancel")
@require_permission("sales.create")
def cancel_payment(intent_id: int):
    intent = payment_intent_service.cancel(intent_id, auth_service.current_user())
    return jsonify(_intent_json(intent)), 200
