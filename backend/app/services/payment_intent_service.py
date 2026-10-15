"""Start / poll / cancel a Razorpay card or UPI payment; completes the sale when Razorpay confirms."""
from __future__ import annotations

from app.errors.exceptions import AppError, ConflictError, NotFoundError
from app.extensions import db
from app.models.enums import PaymentIntentStatus, PaymentMethod, SaleStatus
from app.models.payment_intent import PaymentIntent
from app.models.user import User
from app.schemas.sale_schemas import CompleteSaleRequest
from app.services import billing_service, razorpay_gateway as gw, settings_service
from app.utils.transactions import transaction


def _paise(amount) -> int:
    return int(round(amount * 100))


def start(sale_id: int, method: str, actor: User) -> PaymentIntent:
    if settings_service.get_settings().card_upi_mode == "manual":
        raise AppError("Card/UPI is set to manual in Admin → Settings.")
    with transaction():
        sale = billing_service._lock_owned_sale(sale_id, actor)
        billing_service._require_status(sale, SaleStatus.OPEN)
        if not sale.items:
            raise AppError("Cannot take payment for an empty bill.")
        billing_service._recalculate(sale)          # server decides the amount
        _cancel_pending(sale_id)                    # only one live QR/card push per bill

        amount = sale.total
        if method == "upi":
            ref, image = gw.create_upi_qr(_paise(amount), sale.id, f"Bill #{sale.id}")
            intent = PaymentIntent(sale_id=sale.id, method=PaymentMethod.UPI, amount=amount,
                                   provider_ref=ref, qr_image_url=image)
        elif method == "card":
            device = sale.counter.edc_device_id if sale.counter else None
            if not device:
                raise AppError("No card machine is set for this counter. Ask the admin to add it in Counters.")
            ref = gw.push_to_card_machine(_paise(amount), sale.id, device)
            intent = PaymentIntent(sale_id=sale.id, method=PaymentMethod.CARD, amount=amount, provider_ref=ref)
        else:
            raise AppError("Only card or upi can be started here.")
        db.session.add(intent)
    return intent


def check(intent_id: int, actor: User):
    """Asks Razorpay for the status. If paid, completes the sale. Returns (intent, sale_or_None)."""
    intent = _get(intent_id)
    if intent.sale.cashier_id != actor.id:
        raise ConflictError("This payment belongs to another cashier.")
    if intent.status is PaymentIntentStatus.PAID:
        if intent.sale.status is SaleStatus.PAID:
            return intent, intent.sale
        # Money arrived but completing failed last time (e.g. stock ran out): try again, same error if it still fails.
        return intent, _complete(intent, actor)
    if intent.status is not PaymentIntentStatus.PENDING:
        return intent, None

    st = gw.upi_qr_status(intent.provider_ref, _paise(intent.amount)) if intent.method is PaymentMethod.UPI \
        else gw.card_status(intent.provider_ref, _paise(intent.amount))

    if st.state == "pending":
        return intent, None
    if st.state in ("failed", "cancelled"):
        with transaction():
            intent.status = PaymentIntentStatus.FAILED if st.state == "failed" else PaymentIntentStatus.CANCELLED
            intent.failure_reason = st.reason
        return intent, None

    # paid
    if st.paid_paise != _paise(intent.amount):
        raise AppError(f"Amount received (₹{st.paid_paise / 100:.2f}) does not match the bill. Call the manager.")
    with transaction():
        intent.status = PaymentIntentStatus.PAID
        intent.provider_txn_id = st.txn_id
    return intent, _complete(intent, actor)


def _complete(intent: PaymentIntent, actor: User):
    """Completes the sale in its own transaction: stock, bill number, Payment row with Razorpay's txn id."""
    return billing_service.complete(
        intent.sale_id,
        CompleteSaleRequest(method=intent.method.value, reference=intent.provider_txn_id, payment_intent_id=intent.id),
        actor,
    )


def cancel(intent_id: int, actor: User) -> PaymentIntent:
    intent = _get(intent_id)
    if intent.sale.cashier_id != actor.id:
        raise ConflictError("This payment belongs to another cashier.")
    if intent.status is PaymentIntentStatus.PENDING:
        _cancel_at_gateway(intent)
        with transaction():
            intent.status = PaymentIntentStatus.CANCELLED
    return intent


def cancel_pending_for_sale(sale_id: int) -> None:
    """Called when the cart changes / bill is held or voided: the old amount is no longer valid."""
    _cancel_pending(sale_id)


def _cancel_pending(sale_id: int) -> None:
    for old in PaymentIntent.query.filter_by(sale_id=sale_id, status=PaymentIntentStatus.PENDING).all():
        _cancel_at_gateway(old)
        old.status = PaymentIntentStatus.CANCELLED


def _cancel_at_gateway(intent: PaymentIntent) -> None:
    if intent.method is PaymentMethod.UPI:
        gw.close_upi_qr(intent.provider_ref)
    else:
        device = intent.sale.counter.edc_device_id if intent.sale.counter else ""
        gw.cancel_card_push(intent.provider_ref, device)


def _get(intent_id: int) -> PaymentIntent:
    intent = db.session.get(PaymentIntent, intent_id)
    if intent is None:
        raise NotFoundError(f"Payment {intent_id} not found.")
    return intent