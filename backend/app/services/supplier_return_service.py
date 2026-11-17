"""Goods sent back to the supplier after they were stocked (expired, damaged, recalled).

Stock goes down like a write-off, but the supplier owes us the goods' value (PO rate − discount + GST, the same
maths as the bill), so a debit note is made for it:
- it pays down the invoice that billed the batch's GRN, as far as that invoice still has a balance;
- the rest (invoice already paid, or not billed yet) stays as credit with the supplier, shown and applied to later
  invoices like an unused advance.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select

from app.errors.exceptions import BadRequestError, ConflictError
from app.extensions import db
from app.models.enums import SupplierInvoiceStatus, SupplierPaymentMethod, SupplierPaymentType
from app.models.purchase import GoodsReceipt
from app.models.supplier_invoice import SupplierInvoice, SupplierInvoiceGRN
from app.models.supplier_payment import SupplierPayment, SupplierPaymentAllocation
from app.models.supplier_return import SupplierReturn
from app.models.user import User
from app.schemas.inventory_schemas import BatchReturnRequest, SupplierReturnOut
from app.services import audit_service, inventory_service, purchase_service, supplier_invoice_service
from app.utils.dates import business_date
from app.utils.transactions import transaction


def _unique_return_number() -> str:
    today = business_date().strftime("%Y%m%d")
    for _ in range(10):
        code = f"RTN-{today}-{uuid.uuid4().hex[:4].upper()}"
        if db.session.scalar(select(SupplierReturn.id).where(SupplierReturn.return_number == code)) is None:
            return code
    raise ConflictError("Could not generate a unique return number.")


def _grn_invoice(grn_id: int) -> SupplierInvoice | None:
    """The supplier invoice (not cancelled) that bills this GRN, if any."""
    return db.session.scalar(
        select(SupplierInvoice)
        .join(SupplierInvoiceGRN, SupplierInvoiceGRN.supplier_invoice_id == SupplierInvoice.id)
        .where(SupplierInvoiceGRN.goods_receipt_id == grn_id)
        .where(SupplierInvoice.payment_status != SupplierInvoiceStatus.CANCELLED)
    )


def enrich(ret: SupplierReturn) -> SupplierReturnOut:
    out = SupplierReturnOut.model_validate(ret)
    out.supplier_name = ret.supplier.company_name if ret.supplier else ""
    out.product_name = ret.product.name if ret.product else ""
    out.receipt_number = ret.goods_receipt.receipt_number if ret.goods_receipt else ""
    out.applied_to_invoice = sum(
        (Decimal(str(a.allocated_amount)) for a in ret.debit_note.allocations), Decimal("0")
    ) if ret.debit_note else Decimal("0")
    return out


def return_batch(batch_id: int, data: BatchReturnRequest, actor: User, store_ids: set[int] | None) -> SupplierReturn:
    """Sends goods of one batch back to the supplier who delivered it. store_ids: the stores the actor may
    change (None = all)."""
    batch = inventory_service.get_batch(batch_id, store_ids)
    grn = db.session.get(GoodsReceipt, batch.reference_id) if batch.source == "grn" and batch.reference_id else None
    if grn is None:
        raise BadRequestError(
            "Only goods that came in on a goods receipt (GRN) can go back to a supplier. "
            "Use Write off for this batch."
        )
    gri = next((i for i in grn.receipt_items if i.product_id == batch.product_id), None)
    if gri is None:
        raise BadRequestError(f"Goods receipt {grn.receipt_number} has no line for this product.")
    po = grn.purchase_order
    poi = gri.purchase_order_item
    label = batch.batch_number or f"#{batch.id}"

    with transaction():
        qty = inventory_service.take_from_batch(
            batch, data.qty, data.from_godown,
            f"Returned to {po.supplier.company_name} (batch {label}, {grn.receipt_number}): {data.reason}",
            "auto_supplier_return",
        )
        _gross, _disc, _tax = purchase_service._calc_line(qty, poi.unit_price, poi.discount_percent, poi.tax_rate)
        amount = (_gross - _disc + _tax).quantize(Decimal("0.01"))
        if amount <= 0:
            raise BadRequestError("These goods have no value at the PO rate; use Write off instead.")

        number = _unique_return_number()
        note = SupplierPayment(
            supplier_id=po.supplier_id, store_id=batch.store_id, payment_date=business_date(), amount=amount,
            payment_type=SupplierPaymentType.DEBIT_NOTE,
            payment_method=SupplierPaymentMethod.OTHER,  # no money moves; the column is required
            reference_number=number,
            notes=f"Goods returned: {qty} × {poi.product_name} ({grn.receipt_number}): {data.reason}",
            created_by_id=actor.id if actor else None,
        )
        db.session.add(note)
        db.session.flush()

        inv = _grn_invoice(grn.id)
        if inv is not None and inv.payment_status != SupplierInvoiceStatus.PAID:
            use = min(amount, supplier_invoice_service.outstanding(inv))
            if use > 0:
                note.allocations.append(SupplierPaymentAllocation(invoice_id=inv.id, allocated_amount=use))
                supplier_invoice_service.post_payment_to_invoice(inv.id, use)

        ret = SupplierReturn(
            return_number=number, supplier_id=po.supplier_id, store_id=batch.store_id,
            product_id=batch.product_id, batch_id=batch.id, goods_receipt_id=grn.id,
            qty=qty, amount=amount, reason=data.reason, debit_note_id=note.id,
            created_by_id=actor.id if actor else None,
        )
        db.session.add(ret)
        db.session.flush()
        audit_service.log(
            actor, "supplier.return_goods", "supplier_return", ret.id, None,
            {"batch_id": batch.id, "grn": grn.receipt_number, "qty": str(qty), "amount": str(amount),
             "reason": data.reason},
        )
    return ret


def list_returns(supplier_id: int, page: int = 1, per_page: int = 25) -> tuple[list[SupplierReturnOut], int]:
    q = (
        select(SupplierReturn)
        .where(SupplierReturn.supplier_id == supplier_id)
        .order_by(SupplierReturn.created_at.desc(), SupplierReturn.id.desc())
    )
    total = db.session.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.session.scalars(q.offset((page - 1) * per_page).limit(per_page)).all()
    return [enrich(r) for r in rows], total
