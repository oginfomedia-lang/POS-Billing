"""Purchase order CRUD, workflow transitions, goods receiving, and inventory integration."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError, ValidationError
from app.extensions import db
from app.models.enums import InventoryTxnType, PurchaseStatus, SupplierInvoiceStatus, SupplierPaymentMethod
from app.models.purchase import GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from app.models.supplier_payment import SupplierPayment, SupplierPaymentAllocation
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.purchase_schemas import (
    GoodsReceiptCreate,
    GoodsReceiptItemOut,
    GoodsReceiptOut,
    POPaymentEntry,
    POPaymentHistoryOut,
    POPaymentSummary,
    PurchaseDashboard,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    QuickPaymentIn,
)
from app.services import audit_service
from app.utils.transactions import transaction


# ── Helpers ──────────────────────────────────────────────────────────────────

def _unique_po_number() -> str:
    today = date.today().strftime("%Y%m%d")
    for _ in range(10):
        suffix = uuid.uuid4().hex[:4].upper()
        code = f"PO-{today}-{suffix}"
        if db.session.scalar(db.select(PurchaseOrder).where(PurchaseOrder.po_number == code)) is None:
            return code
    raise ConflictError("Could not generate a unique PO number.")


def _unique_receipt_number() -> str:
    today = date.today().strftime("%Y%m%d")
    for _ in range(10):
        suffix = uuid.uuid4().hex[:4].upper()
        code = f"GR-{today}-{suffix}"
        if db.session.scalar(db.select(GoodsReceipt).where(GoodsReceipt.receipt_number == code)) is None:
            return code
    raise ConflictError("Could not generate a unique receipt number.")


def _calc_line(ordered_qty, unit_price, discount_percent, tax_rate):
    """Returns (line_total, line_discount, tax_amount). line_total = qty × price (gross)."""
    qty = Decimal(str(ordered_qty))
    price = Decimal(str(unit_price))
    disc_pct = Decimal(str(discount_percent))
    rate = Decimal(str(tax_rate))

    gross = (qty * price).quantize(Decimal("0.01"))
    disc = (gross * disc_pct / 100).quantize(Decimal("0.01"))
    taxable = gross - disc
    tax = (taxable * rate / 100).quantize(Decimal("0.01"))
    return gross, disc, tax


def _recalc_totals(po: PurchaseOrder) -> None:
    subtotal = Decimal("0.00")
    disc_total = Decimal("0.00")
    tax_total = Decimal("0.00")
    for item in po.items:
        subtotal += Decimal(str(item.line_total))
        disc_total += Decimal(str(item.line_discount))
        tax_total += Decimal(str(item.tax_amount))
    po.subtotal = subtotal
    po.discount_amount = disc_total
    po.tax_amount = tax_total
    shipping = Decimal(str(po.shipping_charges or 0))
    other = Decimal(str(po.other_charges or 0))
    po.grand_total = subtotal - disc_total + tax_total + shipping + other


def _get_invoice_map(po_ids: list[int]) -> dict[int, SupplierInvoice]:
    if not po_ids:
        return {}
    return {
        inv.purchase_order_id: inv
        for inv in db.session.scalars(
            db.select(SupplierInvoice).where(SupplierInvoice.purchase_order_id.in_(po_ids))
        ).all()
    }


def _enrich_po(po: PurchaseOrder, invoice: SupplierInvoice | None = None) -> PurchaseOrderOut:
    out = PurchaseOrderOut.model_validate(po)
    if po.supplier:
        out.supplier_name = po.supplier.company_name
    if po.created_by:
        out.created_by_name = po.created_by.full_name or po.created_by.username
    grand = Decimal(str(po.grand_total))
    if invoice is not None:
        paid = Decimal(str(invoice.amount_paid))
        outstanding = max(grand - paid, Decimal("0"))
        out.amount_paid = paid
        out.outstanding_amount = outstanding
        if outstanding <= Decimal("0.01"):
            out.payment_status = "paid"
        elif invoice.due_date and invoice.due_date < date.today():
            out.payment_status = "overdue"
        elif paid > Decimal("0"):
            out.payment_status = "partially_paid"
        else:
            out.payment_status = "unpaid"
    else:
        out.outstanding_amount = grand
        out.payment_status = "unpaid"
    return out


def _enrich_receipt(receipt: GoodsReceipt) -> GoodsReceiptOut:
    out = GoodsReceiptOut.model_validate(receipt)
    if receipt.received_by:
        out.received_by_name = receipt.received_by.full_name or receipt.received_by.username
    for i, item in enumerate(receipt.receipt_items):
        if item.product:
            out.receipt_items[i].product_name = item.product.name
    return out


# ── Dashboard ─────────────────────────────────────────────────────────────────

def get_dashboard() -> PurchaseDashboard:
    rows = db.session.execute(
        db.select(PurchaseOrder.status, func.count(PurchaseOrder.id))
        .group_by(PurchaseOrder.status)
    ).all()
    counts: dict[str, int] = {r[0].value if hasattr(r[0], "value") else r[0]: r[1] for r in rows}

    total_value_row = db.session.scalar(
        db.select(func.coalesce(func.sum(PurchaseOrder.grand_total), 0))
        .where(PurchaseOrder.status != PurchaseStatus.CANCELLED)
    ) or Decimal("0")

    draft = counts.get("draft", 0)
    ordered = counts.get("ordered", 0)
    partially = counts.get("partially_received", 0)
    received = counts.get("received", 0)
    cancelled = counts.get("cancelled", 0)

    total_paid_row = db.session.scalar(
        db.select(func.coalesce(func.sum(SupplierInvoice.amount_paid), 0))
        .where(SupplierInvoice.purchase_order_id.isnot(None))
    ) or Decimal("0")

    # total_due: sum of grand_total for non-cancelled POs minus allocated payments
    total_due_row = db.session.scalar(
        db.select(
            func.coalesce(func.sum(PurchaseOrder.grand_total), 0)
            - func.coalesce(func.sum(SupplierInvoice.amount_paid), 0)
        )
        .outerjoin(SupplierInvoice, SupplierInvoice.purchase_order_id == PurchaseOrder.id)
        .where(PurchaseOrder.status != PurchaseStatus.CANCELLED)
    ) or Decimal("0")

    return PurchaseDashboard(
        total=sum(counts.values()),
        total_value=Decimal(str(total_value_row)),
        pending=draft + ordered,
        ordered=ordered,
        partially_received=partially,
        received=received,
        cancelled=cancelled,
        total_paid=Decimal(str(total_paid_row)),
        total_due=max(Decimal(str(total_due_row)), Decimal("0")),
    )


# ── List ──────────────────────────────────────────────────────────────────────

def list_purchase_orders(
    page: int = 1,
    per_page: int = 25,
    status: str | None = None,
    supplier_id: int | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    payment_filter: str | None = None,
) -> tuple[list[PurchaseOrder], int]:
    q = db.select(PurchaseOrder).order_by(PurchaseOrder.id.desc())

    if status:
        try:
            q = q.where(PurchaseOrder.status == PurchaseStatus(status))
        except ValueError:
            pass

    if supplier_id:
        q = q.where(PurchaseOrder.supplier_id == supplier_id)

    if search:
        from app.models.supplier import Supplier as S
        pattern = f"%{search}%"
        q = q.outerjoin(S, PurchaseOrder.supplier_id == S.id).where(
            db.or_(
                PurchaseOrder.po_number.ilike(pattern),
                PurchaseOrder.reference_number.ilike(pattern),
                S.company_name.ilike(pattern),
            )
        )

    if date_from:
        q = q.where(PurchaseOrder.purchase_date >= date_from)
    if date_to:
        q = q.where(PurchaseOrder.purchase_date <= date_to)

    if payment_filter == "has_outstanding":
        q = (
            q.outerjoin(SupplierInvoice, SupplierInvoice.purchase_order_id == PurchaseOrder.id)
            .where(PurchaseOrder.status != PurchaseStatus.CANCELLED)
            .where(
                db.or_(
                    SupplierInvoice.id.is_(None),
                    (PurchaseOrder.grand_total - SupplierInvoice.amount_paid) > Decimal("0.01"),
                )
            )
        )
    elif payment_filter == "has_payments":
        q = (
            q.join(SupplierInvoice, SupplierInvoice.purchase_order_id == PurchaseOrder.id)
            .where(SupplierInvoice.amount_paid > 0)
        )

    total = db.session.scalar(db.select(func.count()).select_from(q.subquery()))
    items = list(db.session.scalars(q.offset((page - 1) * per_page).limit(per_page)).all())
    return items, (total or 0)


# ── Get single ────────────────────────────────────────────────────────────────

def get_purchase_order(po_id: int) -> PurchaseOrder:
    po = db.session.get(PurchaseOrder, po_id)
    if po is None:
        raise NotFoundError(f"Purchase order {po_id} not found.")
    return po


# ── Create ────────────────────────────────────────────────────────────────────

def create_purchase_order(data: PurchaseOrderCreate, actor: User | None) -> PurchaseOrder:
    supplier = db.session.get(Supplier, data.supplier_id)
    if supplier is None:
        raise NotFoundError(f"Supplier {data.supplier_id} not found.")
    if not supplier.is_active:
        raise BadRequestError(f"Supplier '{supplier.company_name}' is inactive.")

    repo = ProductRepository()
    with transaction():
        po = PurchaseOrder(
            po_number=_unique_po_number(),
            supplier_id=data.supplier_id,
            store_id=data.store_id,
            purchase_date=data.purchase_date,
            expected_delivery_date=data.expected_delivery_date,
            reference_number=data.reference_number,
            notes=data.notes,
            internal_remarks=data.internal_remarks,
            shipping_charges=getattr(data, "shipping_charges", Decimal("0")) or Decimal("0"),
            other_charges=getattr(data, "other_charges", Decimal("0")) or Decimal("0"),
            shipping_address=getattr(data, "shipping_address", None),
            status=PurchaseStatus.DRAFT,
            created_by_id=actor.id if actor else None,
        )
        db.session.add(po)
        db.session.flush()  # get po.id

        for line in data.items:
            product = repo.get_by_id(line.product_id)
            if product is None:
                raise NotFoundError(f"Product {line.product_id} not found.")
            gross, disc, tax = _calc_line(line.ordered_qty, line.unit_price, line.discount_percent, line.tax_rate)
            item = PurchaseOrderItem(
                purchase_order_id=po.id,
                product_id=product.id,
                product_name=product.name,
                product_sku=product.sku,
                ordered_qty=line.ordered_qty,
                received_qty=Decimal("0"),
                unit_price=line.unit_price,
                discount_percent=line.discount_percent,
                tax_rate=line.tax_rate,
                line_total=gross,
                line_discount=disc,
                tax_amount=tax,
            )
            db.session.add(item)

        db.session.flush()
        _recalc_totals(po)

        audit_service.log(
            actor, "purchase.create", "purchase_order", po.id,
            None,
            {"po_number": po.po_number, "supplier_id": po.supplier_id, "grand_total": str(po.grand_total)},
        )
    return po


# ── Update (draft only) ───────────────────────────────────────────────────────

def update_purchase_order(po_id: int, data: PurchaseOrderUpdate, actor: User | None) -> PurchaseOrder:
    po = get_purchase_order(po_id)
    if po.status != PurchaseStatus.DRAFT:
        raise BadRequestError("Only draft purchase orders can be edited.")

    repo = ProductRepository()
    with transaction():
        old_vals = {"status": po.status.value, "grand_total": str(po.grand_total)}

        if data.supplier_id is not None:
            supplier = db.session.get(Supplier, data.supplier_id)
            if supplier is None:
                raise NotFoundError(f"Supplier {data.supplier_id} not found.")
            if not supplier.is_active:
                raise BadRequestError(f"Supplier '{supplier.company_name}' is inactive.")
            po.supplier_id = data.supplier_id

        for field in ("store_id", "purchase_date", "expected_delivery_date",
                      "reference_number", "notes", "internal_remarks",
                      "shipping_charges", "other_charges", "shipping_address"):
            val = getattr(data, field, None)
            if val is not None:
                setattr(po, field, val)

        if data.items is not None:
            for existing in list(po.items):
                db.session.delete(existing)
            db.session.flush()

            for line in data.items:
                product = repo.get_by_id(line.product_id)
                if product is None:
                    raise NotFoundError(f"Product {line.product_id} not found.")
                gross, disc, tax = _calc_line(line.ordered_qty, line.unit_price, line.discount_percent, line.tax_rate)
                item = PurchaseOrderItem(
                    purchase_order_id=po.id,
                    product_id=product.id,
                    product_name=product.name,
                    product_sku=product.sku,
                    ordered_qty=line.ordered_qty,
                    received_qty=Decimal("0"),
                    unit_price=line.unit_price,
                    discount_percent=line.discount_percent,
                    tax_rate=line.tax_rate,
                    line_total=gross,
                    line_discount=disc,
                    tax_amount=tax,
                )
                db.session.add(item)
            db.session.flush()

        _recalc_totals(po)
        audit_service.log(
            actor, "purchase.update", "purchase_order", po.id,
            old_vals,
            {"grand_total": str(po.grand_total)},
        )
    return po


# ── Place order (draft → ordered) ─────────────────────────────────────────────

def place_order(po_id: int, actor: User | None) -> PurchaseOrder:
    po = get_purchase_order(po_id)
    if po.status != PurchaseStatus.DRAFT:
        raise BadRequestError("Only draft purchase orders can be placed.")
    if not po.items:
        raise BadRequestError("Purchase order has no items.")

    with transaction():
        po.status = PurchaseStatus.ORDERED
        po.ordered_at = datetime.now(timezone.utc)
        po.ordered_by_id = actor.id if actor else None
        audit_service.log(
            actor, "purchase.place_order", "purchase_order", po.id,
            {"status": "draft"},
            {"status": "ordered", "ordered_at": po.ordered_at.isoformat()},
        )
    return po


# ── Submit for approval (draft → pending_approval) ────────────────────────────

def submit_for_approval(po_id: int, actor: User | None) -> PurchaseOrder:
    po = get_purchase_order(po_id)
    if po.status != PurchaseStatus.DRAFT:
        raise BadRequestError("Only draft purchase orders can be submitted for approval.")
    if not po.items:
        raise BadRequestError("Purchase order has no items.")
    with transaction():
        po.status = PurchaseStatus.PENDING_APPROVAL
        audit_service.log(
            actor, "purchase.submit_for_approval", "purchase_order", po.id,
            {"status": "draft"}, {"status": "pending_approval"},
        )
    return po


# ── Approve order (pending_approval → approved) ────────────────────────────────

def approve_order(po_id: int, actor: User | None) -> PurchaseOrder:
    po = get_purchase_order(po_id)
    if po.status != PurchaseStatus.PENDING_APPROVAL:
        raise BadRequestError("Only orders pending approval can be approved.")
    with transaction():
        po.status = PurchaseStatus.APPROVED
        po.approved_at = datetime.now(timezone.utc)
        po.approved_by_id = actor.id if actor else None
        audit_service.log(
            actor, "purchase.approve", "purchase_order", po.id,
            {"status": "pending_approval"}, {"status": "approved"},
        )
    return po


# ── Close order (received → closed) ──────────────────────────────────────────

def close_order(po_id: int, actor: User | None) -> PurchaseOrder:
    po = get_purchase_order(po_id)
    if po.status != PurchaseStatus.RECEIVED:
        raise BadRequestError("Only fully received orders can be closed.")
    with transaction():
        po.status = PurchaseStatus.CLOSED
        po.closed_at = datetime.now(timezone.utc)
        po.closed_by_id = actor.id if actor else None
        audit_service.log(
            actor, "purchase.close", "purchase_order", po.id,
            {"status": "received"}, {"status": "closed"},
        )
    return po


# ── Cancel order ──────────────────────────────────────────────────────────────

def cancel_order(po_id: int, actor: User | None) -> PurchaseOrder:
    po = get_purchase_order(po_id)
    cancellable = (
        PurchaseStatus.DRAFT,
        PurchaseStatus.PENDING_APPROVAL,
        PurchaseStatus.APPROVED,
        PurchaseStatus.ORDERED,
    )
    if po.status not in cancellable:
        raise BadRequestError(
            f"Cannot cancel a purchase order in '{po.status.value}' status."
        )
    with transaction():
        old_status = po.status.value
        po.status = PurchaseStatus.CANCELLED
        po.cancelled_at = datetime.now(timezone.utc)
        po.cancelled_by_id = actor.id if actor else None
        audit_service.log(
            actor, "purchase.cancel", "purchase_order", po.id,
            {"status": old_status},
            {"status": "cancelled"},
        )
    return po


# ── Receive goods ─────────────────────────────────────────────────────────────

def receive_goods(po_id: int, data: GoodsReceiptCreate, actor: User | None) -> GoodsReceipt:
    po = get_purchase_order(po_id)
    if po.status not in (PurchaseStatus.ORDERED, PurchaseStatus.PARTIALLY_RECEIVED):
        raise BadRequestError(
            f"Cannot receive goods for a purchase order in '{po.status.value}' status."
        )
    if not po.store_id:
        raise BadRequestError(
            "This purchase order has no destination store set. "
            "Edit the PO and select a store before receiving goods."
        )

    # Index items for fast lookup
    item_map: dict[int, PurchaseOrderItem] = {i.id: i for i in po.items}

    # Validate each receipt line before starting DB work
    for ri in data.items:
        poi = item_map.get(ri.purchase_order_item_id)
        if poi is None:
            raise ValidationError(
                f"Item {ri.purchase_order_item_id} does not belong to PO {po.po_number}."
            )
        outstanding = Decimal(str(poi.ordered_qty)) - Decimal(str(poi.received_qty))
        if Decimal(str(ri.qty_received)) > outstanding:
            raise ValidationError(
                f"Cannot receive {ri.qty_received} of '{poi.product_name}': "
                f"only {outstanding} outstanding."
            )

    inv_repo = InventoryRepository()

    with transaction():
        receipt = GoodsReceipt(
            purchase_order_id=po.id,
            receipt_number=_unique_receipt_number(),
            received_at=data.received_at or datetime.now(timezone.utc),
            received_by_id=actor.id if actor else None,
            notes=data.notes,
        )
        db.session.add(receipt)
        db.session.flush()  # get receipt.id

        for ri in data.items:
            poi = item_map[ri.purchase_order_item_id]
            qty = Decimal(str(ri.qty_received))

            gr_item = GoodsReceiptItem(
                goods_receipt_id=receipt.id,
                purchase_order_item_id=poi.id,
                product_id=poi.product_id,
                qty_received=qty,
                qty_accepted=ri.qty_accepted if ri.qty_accepted is not None else qty,
                qty_rejected=ri.qty_rejected,
                qty_damaged=ri.qty_damaged,
                batch_number=ri.batch_number,
                mfg_date=ri.mfg_date,
                expiry_date=ri.expiry_date,
                remarks=ri.remarks,
            )
            db.session.add(gr_item)

            poi.received_qty = Decimal(str(poi.received_qty)) + qty

            # Update inventory
            inv_row = inv_repo.lock_or_create(po.store_id, poi.product_id)
            inv_row.qty_on_hand = Decimal(str(inv_row.qty_on_hand)) + qty
            inv_repo.add_transaction(
                po.store_id, poi.product_id,
                InventoryTxnType.PURCHASE, qty,
                reference_id=receipt.id,
                notes=f"Goods receipt {receipt.receipt_number}",
                expiry_date=ri.expiry_date,
            )

        # Update PO status based on whether everything is received
        all_received = all(
            Decimal(str(i.received_qty)) >= Decimal(str(i.ordered_qty))
            for i in po.items
        )
        po.status = PurchaseStatus.RECEIVED if all_received else PurchaseStatus.PARTIALLY_RECEIVED

        audit_service.log(
            actor, "purchase.receive_goods", "purchase_order", po.id,
            {"status": "ordered"},
            {
                "status": po.status.value,
                "receipt_number": receipt.receipt_number,
                "items_count": len(data.items),
            },
        )
    return receipt


# ── Payment summary ───────────────────────────────────────────────────────────

def get_payment_summary(po_id: int) -> POPaymentSummary:
    po = get_purchase_order(po_id)
    invoice = db.session.scalar(
        db.select(SupplierInvoice).where(SupplierInvoice.purchase_order_id == po_id)
    )
    grand = Decimal(str(po.grand_total))
    if invoice is None:
        return POPaymentSummary(
            po_id=po_id,
            grand_total=grand,
            total_paid=Decimal("0"),
            outstanding=grand,
            invoice_count=0,
            payment_status="unpaid",
            invoice_id=None,
        )
    paid = Decimal(str(invoice.amount_paid))
    outstanding = grand - paid
    if paid <= 0:
        status = "unpaid"
    elif outstanding <= Decimal("0.01"):
        status = "paid"
    else:
        status = "partially_paid"
    return POPaymentSummary(
        po_id=po_id,
        grand_total=grand,
        total_paid=paid,
        outstanding=max(outstanding, Decimal("0")),
        invoice_count=1,
        payment_status=status,
        invoice_id=invoice.id,
    )


# ── Quick payment ─────────────────────────────────────────────────────────────

def quick_payment(po_id: int, data: QuickPaymentIn, actor) -> POPaymentSummary:
    po = get_purchase_order(po_id)
    amount = Decimal(str(data.amount))
    pdate = data.payment_date or date.today()

    with transaction():
        invoice = db.session.scalar(
            db.select(SupplierInvoice).where(SupplierInvoice.purchase_order_id == po_id)
        )
        if invoice is None:
            invoice = SupplierInvoice(
                supplier_id=po.supplier_id,
                purchase_order_id=po.id,
                store_id=po.store_id,
                invoice_number=f"INV-{po.po_number}",
                invoice_date=pdate,
                subtotal=po.subtotal,
                tax_amount=po.tax_amount,
                other_charges=po.other_charges or Decimal("0"),
                grand_total=po.grand_total,
                amount_paid=Decimal("0"),
                payment_status=SupplierInvoiceStatus.UNPAID,
                created_by_id=actor.id if actor else None,
            )
            db.session.add(invoice)
            db.session.flush()

        outstanding = Decimal(str(invoice.grand_total)) - Decimal(str(invoice.amount_paid))
        if amount > outstanding:
            raise BadRequestError(
                f"Cannot pay ₹{amount} — only ₹{outstanding} outstanding on this invoice."
            )

        payment = SupplierPayment(
            supplier_id=po.supplier_id,
            store_id=po.store_id,
            payment_date=pdate,
            amount=amount,
            payment_method=SupplierPaymentMethod(data.payment_method),
            reference_number=data.reference_number,
            notes=data.notes,
            created_by_id=actor.id if actor else None,
        )
        db.session.add(payment)
        db.session.flush()

        db.session.add(SupplierPaymentAllocation(
            payment_id=payment.id,
            invoice_id=invoice.id,
            allocated_amount=amount,
        ))

        new_paid = Decimal(str(invoice.amount_paid)) + amount
        invoice.amount_paid = new_paid
        remaining = Decimal(str(invoice.grand_total)) - new_paid
        invoice.payment_status = (
            SupplierInvoiceStatus.PAID
            if remaining <= Decimal("0.01")
            else SupplierInvoiceStatus.PARTIALLY_PAID
        )

        audit_service.log(
            actor, "purchase.quick_payment", "purchase_order", po.id,
            {"grand_total": str(po.grand_total)},
            {"payment_amount": str(amount), "invoice_id": invoice.id},
        )

    return get_payment_summary(po_id)


# ── Payment history ──────────────────────────────────────────────────────────

def get_payment_history(po_id: int) -> POPaymentHistoryOut:
    po = get_purchase_order(po_id)
    supplier_name = po.supplier.company_name if po.supplier else ""
    grand = Decimal(str(po.grand_total))

    invoice = db.session.scalar(
        db.select(SupplierInvoice).where(SupplierInvoice.purchase_order_id == po_id)
    )

    if invoice is None:
        return POPaymentHistoryOut(
            po_id=po_id,
            po_number=po.po_number,
            supplier_name=supplier_name,
            grand_total=grand,
            total_paid=Decimal("0"),
            outstanding=grand,
            payment_status="unpaid",
            invoice_number=None,
            invoice_id=None,
            entries=[],
        )

    # Load all allocations for this invoice, with their payments, sorted by date then id
    allocations = db.session.execute(
        db.select(SupplierPaymentAllocation, SupplierPayment)
        .join(SupplierPayment, SupplierPaymentAllocation.payment_id == SupplierPayment.id)
        .where(SupplierPaymentAllocation.invoice_id == invoice.id)
        .order_by(SupplierPayment.payment_date.asc(), SupplierPayment.id.asc())
    ).all()

    entries: list[POPaymentEntry] = []
    running = Decimal("0")
    for alloc, payment in allocations:
        allocated = Decimal(str(alloc.allocated_amount))
        if not payment.is_voided:
            running += allocated
        balance = max(grand - running, Decimal("0"))
        method = (
            payment.payment_method.value
            if hasattr(payment.payment_method, "value")
            else str(payment.payment_method)
        )
        created_by_name = ""
        if payment.created_by:
            created_by_name = payment.created_by.full_name or payment.created_by.username or ""
        entries.append(POPaymentEntry(
            payment_id=payment.id,
            payment_date=payment.payment_date,
            amount=Decimal(str(payment.amount)),
            allocated_amount=allocated,
            payment_method=method,
            reference_number=payment.reference_number,
            notes=payment.notes,
            is_voided=payment.is_voided,
            created_by_name=created_by_name,
            running_total_paid=running,
            balance_after=balance,
        ))

    paid = Decimal(str(invoice.amount_paid))
    outstanding = max(grand - paid, Decimal("0"))
    status_val = (
        invoice.payment_status.value
        if hasattr(invoice.payment_status, "value")
        else str(invoice.payment_status)
    )
    return POPaymentHistoryOut(
        po_id=po_id,
        po_number=po.po_number,
        supplier_name=supplier_name,
        grand_total=grand,
        total_paid=paid,
        outstanding=outstanding,
        payment_status=status_val,
        invoice_number=invoice.invoice_number,
        invoice_id=invoice.id,
        entries=entries,
    )


# ── Receipts ──────────────────────────────────────────────────────────────────

def get_receipts(po_id: int) -> list[GoodsReceipt]:
    get_purchase_order(po_id)  # validates existence
    return list(
        db.session.scalars(
            db.select(GoodsReceipt)
            .where(GoodsReceipt.purchase_order_id == po_id)
            .order_by(GoodsReceipt.id)
        ).all()
    )
