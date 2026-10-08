"""create_draft(), add_item(), update_item(), remove_item(), set_manual_discount(), hold(), resume(),
void(), complete().

Every mutation locks the sale row (SELECT ... FOR UPDATE) and recalculates totals
before committing, so the sale returned to the client always has correct totals.
"""
from __future__ import annotations

from app.errors.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.extensions import db
from app.models.enums import SaleStatus, UserRole
from app.models.sale import Sale, SaleItem
from app.models.user import User
from app.repositories.product_repository import ProductRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.sale_schemas import (
    AddItemRequest,
    CompleteSaleRequest,
    HoldSaleRequest,
    ManualDiscountRequest,
    UpdateItemRequest,
)
from app.services import (
    audit_service,
    bill_number_service,
    discount_service,
    inventory_service,
    payment_service,
    pricing_service,
)
from app.services.shift_service import require_active_shift
from app.utils.dates import now_ist
from app.utils.money import money_mul, round_money
from app.utils.security import verify_pin
from app.utils.transactions import transaction


def create_draft(actor: User) -> tuple[Sale, bool]:
    """Return (sale, created). Reuses the cashier's open bill so a reload doesn't orphan drafts."""
    shift = require_active_shift(actor.id)
    repo = SaleRepository()
    existing = repo.list_open(shift.id, actor.id)
    if existing:
        return existing[0], False

    with transaction():
        sale = repo.create_draft(shift.id, shift.store_id, shift.counter_id, actor.id)
    return sale, True


def add_item(sale_id: int, data: AddItemRequest, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        _cancel_live_payments(sale.id)

        product = ProductRepository().get_by_id(data.product_id)
        # store_id NULL = product sold in every store.
        if product is None or not product.is_active or product.store_id not in (None, sale.store_id):
            raise NotFoundError(f"Product {data.product_id} not found.")

        item = SaleRepository().find_item(sale.id, product.id)
        if item is not None:
            item.qty += data.qty
        else:
            item = SaleItem(
                product=product,
                product_name=product.name,
                unit_price=inventory_service.selling_price(sale.store_id, product),
                tax_rate=product.tax_rate,
                qty=data.qty,
            )
            sale.items.append(item)
        _recalculate(sale)
        
    return sale


def update_item(sale_id: int, item_id: int, data: UpdateItemRequest, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        _cancel_live_payments(sale.id)
        item = _get_item_or_404(sale, item_id)
        item.qty = data.qty
        _recalculate(sale)
    return sale


def remove_item(sale_id: int, item_id: int, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        _cancel_live_payments(sale.id)
        item = _get_item_or_404(sale, item_id)
        sale.items.remove(item)
        _recalculate(sale)
    return sale


def set_manual_discount(sale_id: int, item_id: int, data: ManualDiscountRequest, actor: User) -> Sale:
    """Counter discount on one line, approved with a manager/admin PIN. amount 0 removes it."""
    approver = _verify_approver(data.approver_username, data.approver_pin)
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        _cancel_live_payments(sale.id)
        item = _get_item_or_404(sale, item_id)
        line_total = money_mul(item.unit_price, item.qty)
        if data.amount > line_total:
            raise AppError(f"The discount can't be more than the line total (₹{line_total}).")

        old = {"item_id": item.id, "amount": str(item.manual_discount), "reason": item.manual_discount_reason}
        if data.amount > 0:
            item.manual_discount = data.amount
            item.manual_discount_reason = data.reason.strip()
            item.manual_discount_by_id = approver.id
        else:
            item.manual_discount = 0
            item.manual_discount_reason = None
            item.manual_discount_by_id = None
        _recalculate(sale)
        audit_service.log(
            actor, "sale.manual_discount", "sale", sale.id, old,
            {
                "item_id": item.id,
                "product": item.product_name,
                "amount": str(item.manual_discount),
                "reason": item.manual_discount_reason,
                "approved_by": approver.username,
            },
        )
    return sale


def _verify_approver(username: str, pin: str) -> User:
    """Manual discounts need a manager or admin to approve with their own PIN."""
    user = UserRepository().get_by_username(username.strip())
    if user is None or not user.is_active or not verify_pin(pin, user.pin_hash):
        raise PermissionDeniedError("Approval failed: wrong manager username or PIN.")
    if user.role not in (UserRole.ADMIN, UserRole.MANAGER):
        raise PermissionDeniedError("Only a manager or admin can approve a discount.")
    return user


def hold(sale_id: int, data: HoldSaleRequest, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        _cancel_live_payments(sale.id)
        if not sale.items:
            raise AppError("Cannot hold an empty bill.")
        sale.status = SaleStatus.HELD
        sale.note = data.note
    return sale


def list_held(actor: User) -> list[Sale]:
    shift = require_active_shift(actor.id)
    return SaleRepository().list_held(shift.id)


def resume(sale_id: int, actor: User) -> Sale:
    shift = require_active_shift(actor.id)
    repo = SaleRepository()
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.HELD)
        if sale.shift_id != shift.id:
            raise ConflictError("This bill was held in a different shift.")

        # Only one open bill at a time: drop empty drafts, refuse if a real one is in progress.
        for other in repo.list_open(shift.id, actor.id):
            if other.items:
                raise ConflictError("Finish or hold the current bill before resuming another.")
            db.session.delete(other)

        sale.status = SaleStatus.OPEN
    return sale


def void(sale_id: int, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN, SaleStatus.HELD)
        _cancel_live_payments(sale.id)
        old_status = sale.status.value
        sale.status = SaleStatus.VOIDED
        audit_service.log(
            actor, "sale.void", "sale", sale.id,
            {"status": old_status}, {"status": sale.status.value, "total": str(sale.total)},
        )
    return sale


def complete(sale_id: int, data: CompleteSaleRequest, actor: User) -> Sale:
    """Validate payment, deduct stock, assign bill number and mark the sale paid — all in one transaction."""
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        if not sale.items:
            raise AppError("Cannot complete an empty bill.")

        _recalculate(sale)
        if data.method in ("card", "upi"):
            _require_paid_intent(sale, data)
        payment = payment_service.build_payment(data.method, sale.total, data.cash_tendered, data.reference)
        inventory_service.deduct_for_sale(sale.store_id, sale.items, sale.id)

        sale.payments.append(payment)
        sale.bill_number = bill_number_service.next_bill_number(sale.store_id, sale.counter.code if sale.counter else None)
        sale.status = SaleStatus.PAID
        sale.completed_at = now_ist()
        audit_service.log(
            actor, "sale.complete", "sale", sale.id, None,
            {"bill_number": sale.bill_number, "total": str(sale.total), "method": data.method},
        )
    return sale


def get_sale(sale_id: int) -> Sale:
    sale = SaleRepository().get_by_id(sale_id)
    if sale is None:
        raise NotFoundError(f"Sale {sale_id} not found.")
    return sale


def _lock_owned_sale(sale_id: int, actor: User) -> Sale:
    sale = SaleRepository().get_for_update(sale_id)
    if sale is None:
        raise NotFoundError(f"Sale {sale_id} not found.")
    if sale.cashier_id != actor.id:
        raise PermissionDeniedError("This bill belongs to another cashier.")
    return sale


def _require_status(sale: Sale, *allowed: SaleStatus) -> None:
    if sale.status not in allowed:
        raise ConflictError(f"Bill is {sale.status.value}; this action is not allowed.")


def _cancel_live_payments(sale_id: int) -> None:
    """The bill amount is changing (or the bill is leaving the counter): kill any pending QR / card push."""
    # Imported here, not at the top: payment_intent_service imports billing_service (circular import).
    from app.services import payment_intent_service
    payment_intent_service.cancel_pending_for_sale(sale_id)


def _get_item_or_404(sale: Sale, item_id: int) -> SaleItem:
    for item in sale.items:
        if item.id == item_id:
            return item
    raise NotFoundError(f"Item {item_id} not found on sale {sale.id}.")


def _recalculate(sale: Sale) -> None:
    """Re-prices every line with the offers active now.

    Manual (manager-approved) discounts come first; then only ONE automatic offer is applied to
    the whole bill — the item or bill offer that saves the customer the most. A bill offer's
    minimum is checked against the amount with GST (what the customer sees).
    """
    items = list(sale.items)
    room = []
    for item in items:
        item.line_total = money_mul(item.unit_price, item.qty)
        # A manual discount can't take the line below zero (e.g. qty was reduced after it was given).
        item.manual_discount = min(round_money(item.manual_discount or 0), item.line_total)
        room.append(item.line_total - item.manual_discount)

    with_gst = sum(
        (r + pricing_service.line_amounts(item.unit_price, item.qty, item.tax_rate, item.manual_discount)[1]
         for item, r in zip(items, room)),
        pricing_service.ZERO,
    )
    discounts = discount_service.active_for_store(sale.store_id)
    chosen = discount_service.choose_best_offer(discounts, items, room, with_gst)
    offer = chosen.offer

    sale.bill_offer_id = offer.discount_id if chosen.is_bill_offer else None
    sale.bill_offer_name = offer.name if chosen.is_bill_offer else None
    sale.bill_offer_discount = offer.amount if chosen.is_bill_offer else pricing_service.ZERO

    lines = []
    for item, off in zip(items, chosen.line_amounts):
        on_line = not chosen.is_bill_offer and off > 0
        item.offer_id = offer.discount_id if on_line else None
        item.offer_name = offer.name if on_line else None
        item.offer_discount = off if on_line else pricing_service.ZERO
        item.discount_amount = item.manual_discount + off
        item.line_total, item.tax_amount = pricing_service.line_amounts(
            item.unit_price, item.qty, item.tax_rate, item.discount_amount
        )
        lines.append((item.line_total, item.discount_amount, item.tax_amount))
    totals = pricing_service.bill_totals(lines)
    sale.subtotal = totals["subtotal"]
    sale.discount_amount = totals["discount_amount"]
    sale.tax_amount = totals["tax_amount"]
    sale.total = totals["total"]


def _require_paid_intent(sale: Sale, data: CompleteSaleRequest) -> None:
    from app.models.payment_intent import PaymentIntent
    from app.models.enums import PaymentIntentStatus
    intent = db.session.get(PaymentIntent, data.payment_intent_id) if data.payment_intent_id else None
    if (intent is None or intent.sale_id != sale.id or intent.status is not PaymentIntentStatus.PAID
            or intent.method.value != data.method or intent.amount != sale.total):
        raise AppError("Card/UPI payment is not confirmed by Razorpay for this exact amount.")
