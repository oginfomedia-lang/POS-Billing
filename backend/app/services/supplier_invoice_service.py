"""Supplier invoices, entered by the admin when the supplier's bill arrives.

An invoice bills goods that were actually received: it is tied to GRNs (all from one PO), each GRN can be
on only one invoice, and the bill's file (PDF / photo) is attached. The amount the shop owes on it
(payable_amount) is never more than the value of the goods received, whatever the supplier wrote:
payable = min(invoice total, received value + the invoice's other charges). A difference of more than
₹1 needs a reason and marks the invoice "disputed".

Payments are made against invoices (supplier_payment_service), never against the PO.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError
from app.extensions import db
from app.models.enums import DocumentEntityType, InvoiceVerificationStatus, SupplierInvoiceStatus
from app.models.purchase import GoodsReceipt, PurchaseOrder
from app.models.supplier import Supplier
from app.models.supplier_document import SupplierDocument
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceGRN
from app.models.user import User
from app.schemas.supplier_invoice_schemas import (
    GRNPreviewOut,
    SupplierInvoiceCreate,
    SupplierInvoiceOut,
    SupplierInvoiceUpdate,
)
from app.services import audit_service, upload_service
from app.services.purchase_service import grn_value
from app.utils.transactions import transaction

TOLERANCE = Decimal("1.00")  # rate / round-off differences up to ₹1 are fine
CENT = Decimal("0.01")


def _enrich(inv: SupplierInvoice) -> SupplierInvoiceOut:
    out = SupplierInvoiceOut.model_validate(inv)
    if inv.supplier:
        out.supplier_name = inv.supplier.company_name
    if inv.purchase_order:
        out.po_number = inv.purchase_order.po_number
    out.grn_ids = [g.goods_receipt_id for g in inv.grn_links]
    out.grn_numbers = [g.goods_receipt.receipt_number for g in inv.grn_links if g.goods_receipt]
    out.is_legacy = inv.received_value is None
    if inv.received_value is not None:
        out.difference = Decimal(str(inv.grand_total)) - Decimal(str(inv.other_charges)) - Decimal(str(inv.received_value))
    out.outstanding = max(Decimal(str(inv.payable_amount)) - Decimal(str(inv.amount_paid)), Decimal("0"))
    out.document_id = db.session.scalar(
        select(SupplierDocument.id)
        .where(SupplierDocument.entity_type == DocumentEntityType.SUPPLIER_INVOICE)
        .where(SupplierDocument.entity_id == inv.id)
        .order_by(SupplierDocument.id.desc())  # a replaced bill: the latest file
        .limit(1)
    )
    return out


def enrich(inv: SupplierInvoice) -> SupplierInvoiceOut:
    return _enrich(inv)


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
    if payment_status == "outstanding":  # anything still to pay (the payment screen)
        q = q.where(SupplierInvoice.payment_status.in_([SupplierInvoiceStatus.UNPAID, SupplierInvoiceStatus.PARTIALLY_PAID]))
    elif payment_status:
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


# ── GRN checks ────────────────────────────────────────────────────────────────

def _check_grns(supplier_id: int, grn_ids: list[int], invoice_id: int | None = None) -> tuple[list[GoodsReceipt], PurchaseOrder]:
    """The GRNs must exist, be this supplier's, come from one PO and not be billed on another invoice."""
    ids = list(dict.fromkeys(grn_ids))
    if not ids:
        raise BadRequestError("Choose the goods receipts (GRNs) this invoice is for.")
    grns = []
    for grn_id in ids:
        grn = db.session.get(GoodsReceipt, grn_id)
        if grn is None:
            raise NotFoundError(f"GRN #{grn_id} not found.")
        if grn.purchase_order.supplier_id != supplier_id:
            raise BadRequestError(f"GRN {grn.receipt_number} is goods from another supplier.")
        grns.append(grn)
    if len({g.purchase_order_id for g in grns}) > 1:
        raise BadRequestError("One invoice can only cover goods from one purchase order. Add one invoice per PO.")
    taken = db.session.execute(
        select(GoodsReceipt.receipt_number, SupplierInvoice.invoice_number)
        .join(SupplierInvoiceGRN, SupplierInvoiceGRN.goods_receipt_id == GoodsReceipt.id)
        .join(SupplierInvoice, SupplierInvoice.id == SupplierInvoiceGRN.supplier_invoice_id)
        .where(GoodsReceipt.id.in_(ids))
        .where(SupplierInvoice.id != (invoice_id or 0))
    ).first()
    if taken:
        raise ConflictError(f"GRN {taken[0]} is already billed on invoice {taken[1]}.")
    return grns, grns[0].purchase_order


def preview_grns(supplier_id: int, grn_ids: list[int]) -> GRNPreviewOut:
    grns, po = _check_grns(supplier_id, grn_ids)
    return GRNPreviewOut(
        purchase_order_id=po.id,
        po_number=po.po_number,
        received_value=sum((grn_value(g) for g in grns), Decimal("0")),
        grn_numbers=[g.receipt_number for g in grns],
    )


def _settle_amounts(inv: SupplierInvoice, received: Decimal, reason: str | None) -> None:
    """Sets received value, payable amount, verification and payment status from the invoice amounts."""
    other = Decimal(str(inv.other_charges or 0))
    total = Decimal(str(inv.grand_total))
    difference = total - other - received
    reason = (reason or "").strip() or None
    if abs(difference) > TOLERANCE:
        if not reason:
            raise BadRequestError(
                f"The invoice (₹{total - other} for goods) differs from the goods received "
                f"(₹{received}) by ₹{difference}. Enter the reason for the difference.",
                details={"received_value": str(received), "difference": str(difference)},
            )
        inv.verification_status = InvoiceVerificationStatus.DISPUTED
    else:
        inv.verification_status = InvoiceVerificationStatus.VERIFIED
    inv.received_value = received
    inv.difference_reason = reason
    inv.payable_amount = min(total, received + other)
    _set_payment_status(inv)


def _set_payment_status(inv: SupplierInvoice) -> None:
    paid = Decimal(str(inv.amount_paid))
    payable = Decimal(str(inv.payable_amount))
    if paid > payable + CENT:
        raise BadRequestError(f"₹{paid} is already paid on this invoice; the payable amount can't go below that.")
    if paid >= payable - CENT:
        inv.payment_status = SupplierInvoiceStatus.PAID
    elif paid > 0:
        inv.payment_status = SupplierInvoiceStatus.PARTIALLY_PAID
    else:
        inv.payment_status = SupplierInvoiceStatus.UNPAID


def _default_due_date(supplier: Supplier, invoice_date: date) -> date:
    """From the supplier's payment terms: net_30 = 30 days after the invoice date."""
    terms = getattr(supplier.payment_terms, "value", str(supplier.payment_terms or ""))
    days = int(m.group(1)) if (m := re.search(r"(\d+)", terms)) else 0
    return invoice_date + timedelta(days=days)


# ── Create / update ───────────────────────────────────────────────────────────

def create_invoice(data: SupplierInvoiceCreate, file, actor: User | None) -> SupplierInvoiceOut:
    """Admin enters the supplier's bill: the GRNs it covers, its amounts and the bill's file (required)."""
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
    grns, po = _check_grns(data.supplier_id, data.grn_ids)
    if file is None or not getattr(file, "filename", ""):
        raise BadRequestError("Attach the supplier's invoice (PDF or photo).")

    inv = SupplierInvoice(
        supplier_id=data.supplier_id,
        purchase_order_id=po.id,
        store_id=data.store_id or po.store_id,
        invoice_number=data.invoice_number,
        invoice_date=data.invoice_date,
        due_date=data.due_date or _default_due_date(supplier, data.invoice_date),
        subtotal=data.subtotal,
        tax_amount=data.tax_amount,
        other_charges=data.other_charges,
        grand_total=data.grand_total,
        amount_paid=Decimal("0"),
        notes=data.notes,
        created_by_id=actor.id if actor else None,
    )
    _settle_amounts(inv, sum((grn_value(g) for g in grns), Decimal("0")), data.difference_reason)

    stored = upload_service.store_file(file)
    try:
        with transaction():
            db.session.add(inv)
            db.session.flush()
            for grn in grns:
                db.session.add(SupplierInvoiceGRN(supplier_invoice_id=inv.id, goods_receipt_id=grn.id))
            upload_service.add_document(stored, DocumentEntityType.SUPPLIER_INVOICE, inv.id, "Supplier invoice", actor)
            audit_service.log(
                actor, "supplier_invoice.create", "supplier_invoice", inv.id,
                new_values={
                    "invoice_number": inv.invoice_number, "grand_total": str(inv.grand_total),
                    "received_value": str(inv.received_value), "payable": str(inv.payable_amount),
                    "verification": inv.verification_status.value,
                },
            )
    except Exception:
        upload_service.discard_file(stored)
        raise
    return _enrich(inv)


def update_invoice(invoice_id: int, data: SupplierInvoiceUpdate, actor: User | None) -> SupplierInvoiceOut:
    inv = get_invoice(invoice_id)
    if inv.payment_status == SupplierInvoiceStatus.PAID:
        raise BadRequestError("Cannot edit a fully paid invoice.")
    if inv.payment_status == SupplierInvoiceStatus.CANCELLED:
        raise BadRequestError("This invoice is cancelled.")
    changes = data.model_dump(exclude_unset=True, exclude={"grn_ids", "difference_reason", "verification_status"})
    if "invoice_number" in changes and changes["invoice_number"] != inv.invoice_number:
        dup = db.session.scalar(
            select(SupplierInvoice.id).where(
                SupplierInvoice.supplier_id == inv.supplier_id,
                SupplierInvoice.invoice_number == changes["invoice_number"],
                SupplierInvoice.id != inv.id,
            )
        )
        if dup:
            raise ConflictError(f"Invoice number '{changes['invoice_number']}' already exists for this supplier.")

    with transaction():
        for field, val in changes.items():
            setattr(inv, field, val)
        grns = None
        if data.grn_ids is not None:
            grns, po = _check_grns(inv.supplier_id, data.grn_ids, invoice_id=inv.id)
            for link in list(inv.grn_links):
                db.session.delete(link)
            db.session.flush()
            for grn in grns:
                db.session.add(SupplierInvoiceGRN(supplier_invoice_id=inv.id, goods_receipt_id=grn.id))
            inv.purchase_order_id = po.id
        elif inv.received_value is not None:
            grns = [link.goods_receipt for link in inv.grn_links]

        if grns is not None:  # tied to GRNs: payable follows the goods received
            reason = data.difference_reason if "difference_reason" in data.model_fields_set else inv.difference_reason
            _settle_amounts(inv, sum((grn_value(g) for g in grns), Decimal("0")), reason)
        else:  # old invoice without GRNs: payable is its total
            inv.payable_amount = inv.grand_total
            _set_payment_status(inv)
        if data.verification_status is not None:  # admin resolved (or raised) a dispute
            inv.verification_status = data.verification_status
        audit_service.log(
            actor, "supplier_invoice.update", "supplier_invoice", inv.id, None,
            {"grand_total": str(inv.grand_total), "payable": str(inv.payable_amount)},
        )
    return _enrich(inv)


def cancel_invoice(invoice_id: int, reason: str, actor: User | None) -> SupplierInvoiceOut:
    """A wrong or duplicate bill. Only when nothing is paid on it; its GRNs become free to bill again."""
    inv = get_invoice(invoice_id)
    if inv.payment_status == SupplierInvoiceStatus.CANCELLED:
        raise BadRequestError("This invoice is already cancelled.")
    if Decimal(str(inv.amount_paid)) > 0:
        raise BadRequestError(
            f"₹{inv.amount_paid} is already paid on this invoice. Void those payments first (Payments tab)."
        )
    with transaction():
        grns = [link.goods_receipt.receipt_number for link in inv.grn_links if link.goods_receipt]
        for link in list(inv.grn_links):
            db.session.delete(link)
        inv.payment_status = SupplierInvoiceStatus.CANCELLED
        inv.payable_amount = Decimal("0")
        stamp = f"Cancelled: {reason.strip()}"
        inv.notes = f"{inv.notes}\n{stamp}" if inv.notes else stamp
        audit_service.log(
            actor, "supplier_invoice.cancel", "supplier_invoice", inv.id, None,
            {"invoice_number": inv.invoice_number, "reason": reason.strip(), "released_grns": grns},
        )
    return _enrich(inv)


# ── Payment bookkeeping (called by supplier_payment_service) ──────────────────

def post_payment_to_invoice(invoice_id: int, amount: Decimal) -> None:
    inv = get_invoice(invoice_id)
    inv.amount_paid = Decimal(str(inv.amount_paid)) + amount
    _set_payment_status(inv)


def reverse_payment_from_invoice(invoice_id: int, amount: Decimal) -> None:
    """Called when a payment is voided; reverses the amount_paid on invoice."""
    inv = get_invoice(invoice_id)
    inv.amount_paid = max(Decimal("0"), Decimal(str(inv.amount_paid)) - amount)
    _set_payment_status(inv)


def outstanding(inv: SupplierInvoice) -> Decimal:
    return max(Decimal(str(inv.payable_amount)) - Decimal(str(inv.amount_paid)), Decimal("0"))
