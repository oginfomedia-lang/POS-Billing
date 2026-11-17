"""Goods arrived without a purchase order: the supplier's bill is entered once, and in ONE unit of work the app
makes the PO (marked direct, already ordered: no approval, nothing to send), receives the goods (godown or shelf,
cost, batches) and records the invoice with the bill's file (supplier balance, Tally).

Either all three are saved, or none is: the outer transaction() below makes the services' own transaction()
blocks join it (app/utils/transactions.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.errors.exceptions import BadRequestError
from app.extensions import db
from app.models.enums import PurchaseStatus
from app.models.purchase import PurchaseOrder
from app.models.user import User
from app.schemas.purchase_schemas import (
    DirectPurchaseCreate,
    GoodsReceiptCreate,
    GoodsReceiptItemCreate,
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
)
from app.schemas.supplier_invoice_schemas import SupplierInvoiceCreate, SupplierInvoiceOut
from app.services import audit_service, purchase_service, supplier_invoice_service
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
                                        unit_price=line.unit_price, tax_rate=line.tax_rate)
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

        audit_service.log(
            actor, "purchase.direct", "purchase_order", po.id, None,
            {"po_number": po.po_number, "receipt": receipt.receipt_number, "invoice": data.invoice_number},
        )
    return po, invoice
