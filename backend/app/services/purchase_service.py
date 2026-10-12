"""Purchase order CRUD, workflow transitions, goods receiving, and inventory integration."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError, ValidationError
from app.extensions import db
from app.models.enums import InventoryTxnType, PurchaseStatus
from app.models.purchase import GoodsReceipt, GoodsReceiptItem, PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.product_repository import ProductRepository
from app.schemas.purchase_schemas import (
    GoodsReceiptCreate,
    GoodsReceiptItemOut,
    GoodsReceiptOut,
    PurchaseDashboard,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
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
    po.grand_total = subtotal - disc_total + tax_total


def _enrich_po(po: PurchaseOrder) -> PurchaseOrderOut:
    out = PurchaseOrderOut.model_validate(po)
    if po.supplier:
        out.supplier_name = po.supplier.company_name
    if po.created_by:
        out.created_by_name = po.created_by.full_name or po.created_by.username
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

    return PurchaseDashboard(
        total=sum(counts.values()),
        total_value=Decimal(str(total_value_row)),
        pending=draft + ordered,
        ordered=ordered,
        partially_received=partially,
        received=received,
        cancelled=cancelled,
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
                      "reference_number", "notes", "internal_remarks"):
            val = getattr(data, field)
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


# ── Cancel order ──────────────────────────────────────────────────────────────

def cancel_order(po_id: int, actor: User | None) -> PurchaseOrder:
    po = get_purchase_order(po_id)
    if po.status not in (PurchaseStatus.DRAFT, PurchaseStatus.ORDERED):
        raise BadRequestError(
            f"Cannot cancel a purchase order in '{po.status.value}' status. "
            "Only draft or ordered POs can be cancelled."
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
                expiry_date=ri.expiry_date,
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
