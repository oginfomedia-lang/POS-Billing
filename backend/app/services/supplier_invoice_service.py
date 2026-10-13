"""Supplier invoice CRUD and payment-status tracking."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError
from app.extensions import db
from app.models.enums import InvoiceVerificationStatus, SupplierInvoiceStatus
from app.models.purchase import GoodsReceipt
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceGRN
from app.models.user import User
from app.schemas.common import PagedResponse
from app.schemas.supplier_invoice_schemas import (
    SupplierInvoiceCreate,
    SupplierInvoiceOut,
    SupplierInvoiceUpdate,
)
from app.services import audit_service
from app.utils.transactions import transaction


def _enrich(inv: SupplierInvoice) -> SupplierInvoiceOut:
    out = SupplierInvoiceOut.model_validate(inv)
    if inv.supplier:
        out.supplier_name = inv.supplier.company_name
    if inv.purchase_order:
        out.po_number = inv.purchase_order.po_number
    out.grn_ids = [g.goods_receipt_id for g in inv.grn_links]
    out.outstanding = Decimal(str(inv.grand_total)) - Decimal(str(inv.amount_paid))
    return out


def get_invoice(invoice_id: int) -> SupplierInvoice:
    inv = db.session.get(SupplierInvoice, invoice_id)
    if not inv:
        raise NotFoundError(f"Supplier invoice #{invoice_id} not found.")
    return inv


def list_invoices(
    supplier_id: int | None = None,
    payment_status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[SupplierInvoiceOut], int]:
    q = select(SupplierInvoice).order_by(SupplierInvoice.invoice_date.desc(), SupplierInvoice.id.desc())
    if supplier_id:
        q = q.where(SupplierInvoice.supplier_id == supplier_id)
    if payment_status:
        try:
            q = q.where(SupplierInvoice.payment_status == SupplierInvoiceStatus(payment_status))
        except ValueError:
            pass
    if date_from:
        q = q.where(SupplierInvoice.invoice_date >= date_from)
    if date_to:
        q = q.where(SupplierInvoice.invoice_date <= date_to)
    total = db.session.scalar(select(func.count()).select_from(q.subquery())) or 0
    items = list(db.session.scalars(q.offset((page - 1) * per_page).limit(per_page)).all())
    return [_enrich(i) for i in items], total


def create_invoice(data: SupplierInvoiceCreate, actor: User | None) -> SupplierInvoiceOut:
    supplier = db.session.get(Supplier, data.supplier_id)
    if not supplier:
        raise NotFoundError(f"Supplier #{data.supplier_id} not found.")
    dup = db.session.scalar(
        select(SupplierInvoice).where(
            SupplierInvoice.supplier_id == data.supplier_id,
            SupplierInvoice.invoice_number == data.invoice_number,
        )
    )
    if dup:
        raise ConflictError(
            f"Invoice number '{data.invoice_number}' already exists for this supplier."
        )
    with transaction():
        inv = SupplierInvoice(
            supplier_id=data.supplier_id,
            purchase_order_id=data.purchase_order_id,
            store_id=data.store_id,
            invoice_number=data.invoice_number,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            subtotal=data.subtotal,
            tax_amount=data.tax_amount,
            other_charges=data.other_charges,
            grand_total=data.grand_total,
            notes=data.notes,
            created_by_id=actor.id if actor else None,
        )
        db.session.add(inv)
        db.session.flush()
        for grn_id in data.grn_ids:
            grn = db.session.get(GoodsReceipt, grn_id)
            if grn is None:
                raise NotFoundError(f"GRN #{grn_id} not found.")
            db.session.add(SupplierInvoiceGRN(supplier_invoice_id=inv.id, goods_receipt_id=grn_id))
        audit_service.log(
            actor, "supplier_invoice.create", "supplier_invoice", inv.id,
            new_values={"invoice_number": inv.invoice_number, "grand_total": str(inv.grand_total)},
        )
    return _enrich(inv)


def update_invoice(invoice_id: int, data: SupplierInvoiceUpdate, actor: User | None) -> SupplierInvoiceOut:
    inv = get_invoice(invoice_id)
    if inv.payment_status == SupplierInvoiceStatus.PAID:
        raise BadRequestError("Cannot edit a fully paid invoice.")
    with transaction():
        for field, val in data.model_dump(exclude_unset=True, exclude={"grn_ids"}).items():
            setattr(inv, field, val)
        if data.grn_ids is not None:
            for link in list(inv.grn_links):
                db.session.delete(link)
            db.session.flush()
            for grn_id in data.grn_ids:
                grn = db.session.get(GoodsReceipt, grn_id)
                if grn is None:
                    raise NotFoundError(f"GRN #{grn_id} not found.")
                db.session.add(SupplierInvoiceGRN(supplier_invoice_id=inv.id, goods_receipt_id=grn_id))
        audit_service.log(actor, "supplier_invoice.update", "supplier_invoice", inv.id, None, None)
    return _enrich(inv)


def post_payment_to_invoice(invoice_id: int, amount: Decimal) -> None:
    """Called by payment service after allocating funds; updates invoice payment_status."""
    inv = get_invoice(invoice_id)
    inv.amount_paid = Decimal(str(inv.amount_paid)) + amount
    total = Decimal(str(inv.grand_total))
    paid = Decimal(str(inv.amount_paid))
    if paid >= total:
        inv.payment_status = SupplierInvoiceStatus.PAID
    elif paid > 0:
        inv.payment_status = SupplierInvoiceStatus.PARTIALLY_PAID


def reverse_payment_from_invoice(invoice_id: int, amount: Decimal) -> None:
    """Called when a payment is voided; reverses the amount_paid on invoice."""
    inv = get_invoice(invoice_id)
    inv.amount_paid = max(Decimal("0"), Decimal(str(inv.amount_paid)) - amount)
    paid = Decimal(str(inv.amount_paid))
    if paid <= 0:
        inv.payment_status = SupplierInvoiceStatus.UNPAID
    else:
        inv.payment_status = SupplierInvoiceStatus.PARTIALLY_PAID
