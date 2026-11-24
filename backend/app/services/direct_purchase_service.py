"""Goods arrived without a purchase order: the supplier's bill is entered once, and in ONE unit of work the app
makes the PO (marked direct, already ordered: no approval, nothing to send), receives the goods (godown or shelf,
cost, batches) and records the invoice with the bill's file (supplier balance, Tally).

Either all three are saved, or none is: the outer transaction() below makes the services' own transaction()
blocks join it (app/utils/transactions.py).
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from werkzeug.datastructures import FileStorage

from app.errors.exceptions import BadRequestError
from app.extensions import db
from app.models.enums import DocumentEntityType, PurchaseStatus, SupplierInvoiceStatus
from app.models.inventory import StockBatch
from app.models.purchase import PurchaseOrder
from app.models.supplier_document import SupplierDocument
from app.models.supplier_invoice import SupplierInvoice
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.purchase_schemas import (
    DirectPurchaseCreate,
    DirectPurchaseEditLine,
    DirectPurchaseEditOut,
    GoodsReceiptCreate,
    GoodsReceiptItemCreate,
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
)
from app.schemas.supplier_invoice_schemas import SupplierInvoiceCreate, SupplierInvoiceOut
from app.services import (
    audit_service,
    bill_matching_service,
    bill_ocr_service,
    inventory_service,
    purchase_service,
    supplier_invoice_service,
    upload_service,
)
from app.utils.transactions import transaction


def create_direct_purchase(data: DirectPurchaseCreate, file, actor: User) -> tuple[PurchaseOrder, SupplierInvoiceOut]:
    # Cheap checks first, before anything is written.
    if file is None or not getattr(file, "filename", ""):
        raise BadRequestError("Attach the supplier's invoice (PDF or photo).")

    with transaction():  # the unit of work: everything below commits together at the end, or nothing does
        # 1. The PO, from the bill's lines.
        po = purchase_service.create_purchase_order(PurchaseOrderCreate(
            supplier_id=data.supplier_id,
            store_id=data.store_id,
            purchase_date=data.invoice_date,
            reference_number=data.invoice_number,
            notes=data.notes,
            items=[
                PurchaseOrderItemCreate(product_id=line.product_id, ordered_qty=line.qty,
                                        unit_price=line.unit_price, discount_percent=line.discount_percent, tax_rate=line.tax_rate)
                for line in data.items
            ],
        ), actor)

        # 2. Ordered straight away: no approval, no email to the supplier (the goods are already here).
        po.is_direct = True
        po.status = PurchaseStatus.ORDERED
        po.ordered_at = datetime.now(timezone.utc)
        po.ordered_by_id = actor.id
        db.session.flush()

        # 3. Receive everything on the bill. Each bill line is matched to its PO line by product.
        lines = {line.product_id: line for line in data.items}
        receipt = purchase_service.receive_goods(po.id, GoodsReceiptCreate(
            notes=f"Direct purchase: bill {data.invoice_number}",
            items=[
                GoodsReceiptItemCreate(
                    purchase_order_item_id=item.id,
                    qty_received=lines[item.product_id].qty,
                    batch_number=lines[item.product_id].batch_number,
                    expiry_date=lines[item.product_id].expiry_date,
                    to_shop=lines[item.product_id].to_shop,
                    mrp=lines[item.product_id].mrp,
                    hsn_code=lines[item.product_id].hsn_code,
                    # Same as the PO line, so nothing is "corrected"; a new product takes it as its selling GST.
                    bill_tax_rate=lines[item.product_id].tax_rate,
                )
                for item in po.items
            ],
        ), actor)

        # 4. The invoice for that receipt, with the bill's file.
        invoice = supplier_invoice_service.create_invoice(SupplierInvoiceCreate(
            supplier_id=data.supplier_id,
            store_id=data.store_id,
            invoice_number=data.invoice_number,
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            other_charges=data.other_charges,
            grand_total=data.grand_total,
            notes=data.notes,
            grn_ids=[receipt.id],
            difference_reason=data.difference_reason,
        ), file, actor)

        # 5. Lines read from the bill: remember what this supplier calls each product, for their next bill.
        bill_matching_service.remember(
            data.supplier_id, [(line.bill_description, line.product_id) for line in data.items if line.bill_description]
        )

        audit_service.log(
            actor, "purchase.direct", "purchase_order", po.id, None,
            {"po_number": po.po_number, "receipt": receipt.receipt_number, "invoice": data.invoice_number},
        )
    return po, invoice


# ── Correcting a saved direct purchase ───────────────────────────────────────

def _editable(po_id: int) -> tuple[PurchaseOrder, SupplierInvoice, list[StockBatch]]:
    """A saved direct purchase can be corrected only while nothing has happened to it since."""
    po = purchase_service.get_purchase_order(po_id)
    if not po.is_direct or po.status != PurchaseStatus.RECEIVED:
        raise BadRequestError("Only a saved direct purchase can be corrected.")
    invoice = db.session.scalar(select(SupplierInvoice).where(
        SupplierInvoice.purchase_order_id == po.id,
        SupplierInvoice.payment_status != SupplierInvoiceStatus.CANCELLED,
    ))
    if invoice is None:
        raise BadRequestError("This purchase has no invoice to correct.")
    if Decimal(str(invoice.amount_paid)) > 0:
        raise BadRequestError(
            f"₹{invoice.amount_paid} is already paid on bill {invoice.invoice_number}. Void that payment first.")
    batches = list(db.session.scalars(select(StockBatch).where(
        StockBatch.source == "grn", StockBatch.reference_id.in_([r.id for r in po.receipts]))))
    for b in batches:
        if Decimal(str(b.qty_remaining)) != Decimal(str(b.qty_received)):
            raise BadRequestError(
                f"Some '{b.product.name}' from this bill is already sold, returned or written off, so the bill "
                f"can't be corrected. Fix it with a supplier return or a stock adjustment.")
    return po, invoice, batches


def _bill_document(invoice: SupplierInvoice) -> SupplierDocument | None:
    return db.session.scalar(
        select(SupplierDocument)
        .where(SupplierDocument.entity_type == DocumentEntityType.SUPPLIER_INVOICE,
               SupplierDocument.entity_id == invoice.id)
        .order_by(SupplierDocument.id.desc()).limit(1))


def get_for_edit(po_id: int) -> DirectPurchaseEditOut:
    po, invoice, _ = _editable(po_id)
    received = {ri.purchase_order_item_id: ri for r in po.receipts for ri in r.receipt_items}
    doc = _bill_document(invoice)
    items = []
    for poi in po.items:
        ri = received.get(poi.id)
        items.append(DirectPurchaseEditLine(
            product=bill_ocr_service._product_out(poi.product),
            qty=float(poi.ordered_qty), unit_price=float(poi.unit_price),
            discount_percent=float(poi.discount_percent), tax_rate=float(poi.tax_rate),
            mrp=float(poi.product.mrp) if poi.product.mrp is not None else None,
            hsn_code=poi.product.hsn_code,
            batch_number=ri.batch_number if ri else None,
            expiry_date=ri.expiry_date if ri else None,
        ))
    return DirectPurchaseEditOut(
        po_id=po.id, po_number=po.po_number, supplier_id=po.supplier_id, store_id=po.store_id,
        invoice_number=invoice.invoice_number, invoice_date=invoice.invoice_date, due_date=invoice.due_date,
        other_charges=float(invoice.other_charges), grand_total=float(invoice.grand_total),
        difference_reason=invoice.difference_reason,
        bill_file_name=doc.original_filename if doc else None,
        items=items,
    )


def update_direct_purchase(po_id: int, data: DirectPurchaseCreate, file: FileStorage | None,
                           actor: User) -> tuple[PurchaseOrder, SupplierInvoiceOut]:
    """Undo the saved bill (stock, invoice, PO) and save the corrected one: all of it, or nothing."""
    old, invoice, batches = _editable(po_id)
    if file is None:
        doc = _bill_document(invoice)
        if doc is None:
            raise BadRequestError("Attach the supplier's invoice (PDF or photo).")
        file = upload_service.open_copy(doc)  # no new file chosen: keep the bill already saved

    with transaction():
        # 1. The goods of the old entry go out of stock again (and out of the average cost).
        repo = InventoryRepository()
        for b in batches:
            row = repo.lock_or_create(b.store_id, b.product_id)
            qty = Decimal(str(b.qty_remaining))
            inventory_service.remove_purchase_cost(row, qty, b.unit_cost)
            inventory_service.take_from_batch(
                b, None, from_godown=Decimal(str(row.godown_qty or 0)) >= qty,
                note=f"Direct purchase {old.po_number} corrected", godown_reason="auto_correction")

        # 2. The old invoice: cancelled, and its number freed for the corrected bill.
        old_number = invoice.invoice_number
        supplier_invoice_service.cancel_invoice(invoice.id, "Corrected: replaced by a new entry", actor)
        invoice.invoice_number = f"{old_number}~{invoice.id}"[:100]

        # 3. The old PO: cancelled.
        old.status = PurchaseStatus.CANCELLED
        old.cancelled_at = datetime.now(timezone.utc)
        old.cancelled_by_id = actor.id
        db.session.flush()

        # 4. The corrected bill, saved exactly like a new one.
        po, new_invoice = create_direct_purchase(data, file, actor)
        audit_service.log(
            actor, "purchase.direct_corrected", "purchase_order", po.id,
            {"po_number": old.po_number, "invoice": old_number},
            {"po_number": po.po_number, "invoice": data.invoice_number},
        )
    return po, new_invoice
