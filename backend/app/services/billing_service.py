"""create_draft(), add_item(), update_item(), remove_item(), hold(), resume(), void(), complete().

Every mutation locks the sale row (SELECT ... FOR UPDATE) and recalculates totals
before committing, so the sale returned to the client always has correct totals.
"""
from __future__ import annotations

from app.errors.exceptions import AppError, ConflictError, NotFoundError, PermissionDeniedError
from app.extensions import db
from app.models.enums import SaleStatus
from app.models.sale import Sale, SaleItem
from app.models.user import User
from app.repositories.product_repository import ProductRepository
from app.repositories.sale_repository import SaleRepository
from app.schemas.sale_schemas import AddItemRequest, CompleteSaleRequest, HoldSaleRequest, UpdateItemRequest
from app.services import audit_service, bill_number_service, inventory_service, payment_service, pricing_service
from app.services.shift_service import require_active_shift
from app.utils.dates import now_ist
from app.utils.transactions import transaction


def create_draft(actor: User) -> tuple[Sale, bool]:
    """Return (sale, created). Reuses the cashier's open bill so a reload doesn't orphan drafts."""
    shift = require_active_shift(actor)
    repo = SaleRepository()
    existing = repo.list_open(shift.id, actor.id)
    if existing:
        return existing[0], False

    with transaction():
        sale = repo.create_draft(shift.id, shift.store_id, shift.counter_id, actor.id)
    return sale, True


def add_item(sale_id: int, data: AddItemRequest, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)

        product = ProductRepository().get_by_id(data.product_id)
        if product is None or not product.is_active:
            raise NotFoundError(f"Product {data.product_id} not found.")

        item = SaleRepository().find_item(sale.id, product.id)
        if item is not None:
            item.qty += data.qty
        else:
            item = SaleItem(
                product_id=product.id,
                product_name=product.name,
                unit_price=product.selling_price,
                tax_rate=product.gst_rate,
                qty=data.qty,
            )
            sale.items.append(item)
        _recalculate(sale)
    return sale


def update_item(sale_id: int, item_id: int, data: UpdateItemRequest, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        item = _get_item_or_404(sale, item_id)
        item.qty = data.qty
        _recalculate(sale)
    return sale


def remove_item(sale_id: int, item_id: int, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        item = _get_item_or_404(sale, item_id)
        sale.items.remove(item)
        _recalculate(sale)
    return sale


def hold(sale_id: int, data: HoldSaleRequest, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        if not sale.items:
            raise AppError("Cannot hold an empty bill.")
        sale.status = SaleStatus.HELD
        sale.note = data.note
    return sale


def list_held(actor: User) -> list[Sale]:
    shift = require_active_shift(actor)
    return SaleRepository().list_held(shift.id)


def resume(sale_id: int, actor: User) -> Sale:
    shift = require_active_shift(actor)
    repo = SaleRepository()
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.HELD)
        if sale.shift_id != shift.id:
            raise ConflictError("This bill was held in a different shift.")

        # Only one open bill at a time: drop empty drafts, refuse if a real one is in progress.
        for other in repo.list_open(shift.id, actor.id):
            if other.items:
                raise ConflictError("Finish or hold the current bill before resuming another.")
            db.session.delete(other)

        sale.status = SaleStatus.OPEN
    return sale


def void(sale_id: int, actor: User) -> Sale:
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN, SaleStatus.HELD)
        old_status = sale.status.value
        sale.status = SaleStatus.VOIDED
        audit_service.log(
            actor, "sale.void", "sale", sale.id,
            {"status": old_status}, {"status": sale.status.value, "total": str(sale.total)},
        )
    return sale


def complete(sale_id: int, data: CompleteSaleRequest, actor: User) -> Sale:
    """Validate payment, deduct stock, assign bill number and mark the sale paid — all in one transaction."""
    with transaction():
        sale = _lock_owned_sale(sale_id, actor)
        _require_status(sale, SaleStatus.OPEN)
        if not sale.items:
            raise AppError("Cannot complete an empty bill.")

        _recalculate(sale)
        payment = payment_service.build_payment(data.method, sale.total, data.cash_tendered, data.reference)
        inventory_service.deduct_for_sale(sale.store_id, sale.items)

        sale.payments.append(payment)
        sale.bill_number = bill_number_service.next_bill_number(sale.store_id, sale.counter.code)
        sale.status = SaleStatus.PAID
        sale.completed_at = now_ist()
        audit_service.log(
            actor, "sale.complete", "sale", sale.id, None,
            {"bill_number": sale.bill_number, "total": str(sale.total), "method": data.method},
        )
    return sale


def get_sale(sale_id: int) -> Sale:
    sale = SaleRepository().get_by_id(sale_id)
    if sale is None:
        raise NotFoundError(f"Sale {sale_id} not found.")
    return sale


def _lock_owned_sale(sale_id: int, actor: User) -> Sale:
    sale = SaleRepository().get_for_update(sale_id)
    if sale is None:
        raise NotFoundError(f"Sale {sale_id} not found.")
    if sale.cashier_id != actor.id:
        raise PermissionDeniedError("This bill belongs to another cashier.")
    return sale


def _require_status(sale: Sale, *allowed: SaleStatus) -> None:
    if sale.status not in allowed:
        raise ConflictError(f"Bill is {sale.status.value}; this action is not allowed.")


def _get_item_or_404(sale: Sale, item_id: int) -> SaleItem:
    for item in sale.items:
        if item.id == item_id:
            return item
    raise NotFoundError(f"Item {item_id} not found on sale {sale.id}.")


def _recalculate(sale: Sale) -> None:
    lines = []
    for item in sale.items:
        item.line_total, item.tax_amount = pricing_service.line_amounts(item.unit_price, item.qty, item.tax_rate)
        lines.append((item.line_total, item.tax_amount))
    totals = pricing_service.bill_totals(lines, sale.discount_amount or 0)
    sale.subtotal = totals["subtotal"]
    sale.discount_amount = totals["discount_amount"]
    sale.tax_amount = totals["tax_amount"]
    sale.total = totals["total"]
