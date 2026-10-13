"""Supplier payments, made against the supplier's invoices (never against a PO).

- A normal payment ("payment") is split across invoices and must add up exactly; each invoice can be paid
  only up to its balance (= goods received − already paid).
- An advance ("advance") is money paid before the bill arrives (e.g. before delivery). It may go against no
  invoice at all; its unused part is applied to invoices later (apply_advance). Unused advance is shown
  on the supplier page.
- Voiding a payment puts the money back on its invoices.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.errors.exceptions import BadRequestError, NotFoundError
from app.extensions import db
from app.models.enums import SupplierInvoiceStatus, SupplierPaymentType
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from app.models.supplier_payment import SupplierPayment, SupplierPaymentAllocation
from app.models.user import User
from app.schemas.supplier_payment_schemas import (
    PaymentAllocationIn,
    PaymentAllocationOut,
    SupplierPaymentCreate,
    SupplierPaymentOut,
)
from app.services import audit_service, supplier_invoice_service
from app.utils.transactions import transaction


def unallocated(pay: SupplierPayment) -> Decimal:
    """The part of a payment not yet put against any invoice (only advances have one)."""
    if pay.is_voided:
        return Decimal("0")
    used = sum((Decimal(str(a.allocated_amount)) for a in pay.allocations), Decimal("0"))
    return max(Decimal(str(pay.amount)) - used, Decimal("0"))


def _enrich(pay: SupplierPayment) -> SupplierPaymentOut:
    out = SupplierPaymentOut.model_validate(pay)
    if pay.supplier:
        out.supplier_name = pay.supplier.company_name
    enriched_allocs = []
    for a in pay.allocations:
        ao = PaymentAllocationOut.model_validate(a)
        if a.invoice:
            ao.invoice_number = a.invoice.invoice_number
        enriched_allocs.append(ao)
    out.allocations = enriched_allocs
    out.unallocated_amount = unallocated(pay)
    return out


def get_payment(payment_id: int) -> SupplierPayment:
    pay = db.session.get(SupplierPayment, payment_id)
    if not pay:
        raise NotFoundError(f"Supplier payment #{payment_id} not found.")
    return pay


def list_payments(
    supplier_id: int | None = None,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[SupplierPaymentOut], int]:
    q = select(SupplierPayment).order_by(SupplierPayment.payment_date.desc(), SupplierPayment.id.desc())
    if supplier_id:
        q = q.where(SupplierPayment.supplier_id == supplier_id)
    total = db.session.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = list(db.session.scalars(q.offset((page - 1) * per_page).limit(per_page)).all())
    return [_enrich(p) for p in items], total


def advance_balance(supplier_id: int) -> Decimal:
    """Advance money paid to the supplier and not yet applied to an invoice."""
    payments = db.session.scalars(
        select(SupplierPayment).where(
            SupplierPayment.supplier_id == supplier_id,
            SupplierPayment.is_voided.is_(False),
            SupplierPayment.payment_type == SupplierPaymentType.ADVANCE,
        )
    ).all()
    return sum((unallocated(p) for p in payments), Decimal("0"))


def _check_allocations(supplier_id: int, allocations: list[PaymentAllocationIn]) -> None:
    """Each invoice: this supplier's, open, once, and no more than its balance."""
    if len({a.invoice_id for a in allocations}) != len(allocations):
        raise BadRequestError("Each invoice can appear only once in a payment.")
    for alloc in allocations:
        inv = db.session.get(SupplierInvoice, alloc.invoice_id)
        if inv is None:
            raise NotFoundError(f"Invoice #{alloc.invoice_id} not found.")
        if inv.supplier_id != supplier_id:
            raise BadRequestError(f"Invoice #{alloc.invoice_id} does not belong to this supplier.")
        if inv.payment_status in (SupplierInvoiceStatus.PAID, SupplierInvoiceStatus.CANCELLED):
            raise BadRequestError(f"Invoice {inv.invoice_number} is already {inv.payment_status.value}.")
        # Payable = what was received, so this is also "never pay for goods that didn't arrive".
        outstanding = supplier_invoice_service.outstanding(inv)
        if alloc.allocated_amount > outstanding:
            raise BadRequestError(
                f"Invoice {inv.invoice_number}: only ₹{outstanding} is left to pay, not ₹{alloc.allocated_amount}."
            )


def _allocate(pay: SupplierPayment, allocations: list[PaymentAllocationIn]) -> None:
    """Puts money from the payment against invoices (inside the caller's transaction)."""
    existing = {a.invoice_id: a for a in pay.allocations}
    for alloc in allocations:
        amount = Decimal(str(alloc.allocated_amount))
        if alloc.invoice_id in existing:  # topping up an invoice this advance already paid towards
            existing[alloc.invoice_id].allocated_amount = Decimal(str(existing[alloc.invoice_id].allocated_amount)) + amount
        else:
            pay.allocations.append(SupplierPaymentAllocation(invoice_id=alloc.invoice_id, allocated_amount=amount))
        supplier_invoice_service.post_payment_to_invoice(alloc.invoice_id, amount)


def create_payment(data: SupplierPaymentCreate, actor: User | None) -> SupplierPaymentOut:
    supplier = db.session.get(Supplier, data.supplier_id)
    if not supplier:
        raise NotFoundError(f"Supplier #{data.supplier_id} not found.")

    total_allocated = sum((a.allocated_amount for a in data.allocations), Decimal("0"))
    if data.payment_type == SupplierPaymentType.ADVANCE:
        # Money before the bill: may go against no invoice now; the rest is applied later.
        if total_allocated > data.amount:
            raise BadRequestError(
                f"The amounts against the invoices (₹{total_allocated}) are more than the advance (₹{data.amount})."
            )
    else:
        # Every rupee of a normal payment goes against a supplier invoice: the amounts must add up exactly.
        if not data.allocations:
            raise BadRequestError("Choose the invoice(s) this payment is for, or record it as an advance.")
        if total_allocated != data.amount:
            raise BadRequestError(
                f"The amounts against the invoices (₹{total_allocated}) must add up to the payment (₹{data.amount})."
            )
    _check_allocations(data.supplier_id, data.allocations)

    with transaction():
        pay = SupplierPayment(
            supplier_id=data.supplier_id,
            store_id=data.store_id,
            payment_date=data.payment_date,
            amount=data.amount,
            payment_type=data.payment_type,
            payment_method=data.payment_method,
            reference_number=data.reference_number,
            bank_account=data.bank_account,
            notes=data.notes,
            created_by_id=actor.id if actor else None,
        )
        db.session.add(pay)
        db.session.flush()
        _allocate(pay, data.allocations)
        audit_service.log(
            actor, "supplier_payment.create", "supplier_payment", pay.id,
            new_values={
                "supplier_id": data.supplier_id,
                "amount": str(data.amount),
                "type": data.payment_type.value,
                "against_invoices": str(total_allocated),
            },
        )
    return _enrich(pay)


def apply_advance(payment_id: int, allocations: list[PaymentAllocationIn], actor: User | None) -> SupplierPaymentOut:
    """Uses the unused part of an advance to pay invoices that have arrived since."""
    pay = get_payment(payment_id)
    if pay.is_voided:
        raise BadRequestError("This payment is voided.")
    if pay.payment_type != SupplierPaymentType.ADVANCE:
        raise BadRequestError("Only an advance can be applied to invoices later.")
    if not allocations:
        raise BadRequestError("Choose the invoice(s) to apply the advance to.")
    total = sum((a.allocated_amount for a in allocations), Decimal("0"))
    left = unallocated(pay)
    if total > left:
        raise BadRequestError(f"Only ₹{left} of this advance is left to apply, not ₹{total}.")
    _check_allocations(pay.supplier_id, allocations)
    with transaction():
        _allocate(pay, allocations)
        audit_service.log(
            actor, "supplier_payment.apply_advance", "supplier_payment", pay.id, None,
            {"applied": str(total), "invoices": [a.invoice_id for a in allocations]},
        )
    return _enrich(pay)


def void_payment(payment_id: int, actor: User | None) -> SupplierPaymentOut:
    pay = get_payment(payment_id)
    if pay.is_voided:
        raise BadRequestError("Payment is already voided.")
    with transaction():
        for alloc in pay.allocations:
            supplier_invoice_service.reverse_payment_from_invoice(alloc.invoice_id, Decimal(str(alloc.allocated_amount)))
        pay.is_voided = True
        pay.voided_at = datetime.now(timezone.utc)
        pay.voided_by_id = actor.id if actor else None
        audit_service.log(actor, "supplier_payment.void", "supplier_payment", pay.id, None, None)
    return _enrich(pay)
