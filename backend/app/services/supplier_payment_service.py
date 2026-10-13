"""Supplier payment CRUD with invoice allocation."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.errors.exceptions import BadRequestError, NotFoundError
from app.extensions import db
from app.models.enums import SupplierInvoiceStatus
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from app.models.supplier_payment import SupplierPayment, SupplierPaymentAllocation
from app.models.user import User
from app.schemas.supplier_payment_schemas import (
    PaymentAllocationOut,
    SupplierPaymentCreate,
    SupplierPaymentOut,
)
from app.services import audit_service
from app.utils.transactions import transaction


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


def create_payment(data: SupplierPaymentCreate, actor: User | None) -> SupplierPaymentOut:
    supplier = db.session.get(Supplier, data.supplier_id)
    if not supplier:
        raise NotFoundError(f"Supplier #{data.supplier_id} not found.")

    total_allocated = sum(a.allocated_amount for a in data.allocations)
    if total_allocated > data.amount:
        raise BadRequestError(
            f"Allocated amount {total_allocated} exceeds payment amount {data.amount}."
        )

    # Pre-validate invoices
    invoice_map: dict[int, SupplierInvoice] = {}
    for alloc in data.allocations:
        inv = db.session.get(SupplierInvoice, alloc.invoice_id)
        if inv is None:
            raise NotFoundError(f"Invoice #{alloc.invoice_id} not found.")
        if inv.supplier_id != data.supplier_id:
            raise BadRequestError(
                f"Invoice #{alloc.invoice_id} does not belong to this supplier."
            )
        if inv.payment_status == SupplierInvoiceStatus.PAID:
            raise BadRequestError(f"Invoice #{alloc.invoice_id} is already fully paid.")
        outstanding = Decimal(str(inv.grand_total)) - Decimal(str(inv.amount_paid))
        if alloc.allocated_amount > outstanding:
            raise BadRequestError(
                f"Cannot allocate {alloc.allocated_amount} to invoice #{alloc.invoice_id}: "
                f"only {outstanding} outstanding."
            )
        invoice_map[alloc.invoice_id] = inv

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

        for alloc in data.allocations:
            db.session.add(SupplierPaymentAllocation(
                payment_id=pay.id,
                invoice_id=alloc.invoice_id,
                allocated_amount=alloc.allocated_amount,
            ))
            inv = invoice_map[alloc.invoice_id]
            inv.amount_paid = Decimal(str(inv.amount_paid)) + Decimal(str(alloc.allocated_amount))
            total = Decimal(str(inv.grand_total))
            paid = Decimal(str(inv.amount_paid))
            if paid >= total:
                inv.payment_status = SupplierInvoiceStatus.PAID
            elif paid > 0:
                inv.payment_status = SupplierInvoiceStatus.PARTIALLY_PAID

        audit_service.log(
            actor, "supplier_payment.create", "supplier_payment", pay.id,
            new_values={
                "supplier_id": data.supplier_id,
                "amount": str(data.amount),
                "type": data.payment_type.value,
            },
        )
    return _enrich(pay)


def void_payment(payment_id: int, actor: User | None) -> SupplierPaymentOut:
    pay = get_payment(payment_id)
    if pay.is_voided:
        raise BadRequestError("Payment is already voided.")
    with transaction():
        for alloc in pay.allocations:
            inv = db.session.get(SupplierInvoice, alloc.invoice_id)
            if inv:
                inv.amount_paid = max(
                    Decimal("0"),
                    Decimal(str(inv.amount_paid)) - Decimal(str(alloc.allocated_amount)),
                )
                paid = Decimal(str(inv.amount_paid))
                if paid <= 0:
                    inv.payment_status = SupplierInvoiceStatus.UNPAID
                else:
                    inv.payment_status = SupplierInvoiceStatus.PARTIALLY_PAID
        pay.is_voided = True
        pay.voided_at = datetime.now(timezone.utc)
        pay.voided_by_id = actor.id if actor else None
        audit_service.log(actor, "supplier_payment.void", "supplier_payment", pay.id, None, None)
    return _enrich(pay)
