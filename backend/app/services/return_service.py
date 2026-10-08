"""Returns against a paid bill: check the rules, work out the refund, restock, record the credit note.

Rules: a manager/admin approves with their PIN, the cashier has an open shift (the cash comes out
of their drawer), same store as the bill, within the return window, and never more than was sold.
Every refund is paid in cash.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from app.errors.exceptions import AppError, NotFoundError
from app.extensions import db
from app.models.enums import PaymentMethod, SaleStatus
from app.models.returns import SaleReturn, SaleReturnItem
from app.models.sale import Sale, SaleItem
from app.models.user import User
from app.repositories.return_repository import ReturnRepository
from app.repositories.sale_repository import SaleRepository
from app.schemas.return_schemas import (
    BillForMobileOut,
    CreateReturnRequest,
    ReturnableBillOut,
    ReturnableLineOut,
    ReturnItemOut,
    ReturnOut,
)
from app.schemas.sale_schemas import GstSummaryRow
from app.services import audit_service, billing_service, inventory_service, pricing_service, settings_service
from app.services.shift_service import require_active_shift
from app.utils.dates import IST, now_ist
from app.utils.money import round_money
from app.utils.phone import mask_mobile, normalize_mobile
from app.utils.transactions import transaction

ZERO = Decimal("0")
NOTHING_RETURNED = (ZERO, ZERO, ZERO, ZERO)  # (qty, line_total, discount_amount, tax_amount)


def returnable_bill(bill_number: str, actor: User) -> ReturnableBillOut:
    """The bill with what can still be returned on each line. Changes nothing."""
    sale = _paid_sale(bill_number)
    window = settings_service.get_settings().return_window_days
    done = ReturnRepository().returned_by_item(sale.id)

    lines = []
    for item in sale.items:
        qty_r, line_r, disc_r, tax_r = done.get(item.id, NOTHING_RETURNED)
        lines.append(ReturnableLineOut(
            sale_item_id=item.id,
            product_id=item.product_id,
            product_name=item.product_name,
            hsn_code=item.hsn_code,
            unit_price=item.unit_price,
            tax_rate=item.tax_rate,
            is_variable_weight=_is_weighed(item),
            qty_sold=item.qty,
            qty_returned=qty_r,
            qty_returnable=item.qty - qty_r,
            line_total=item.line_total,
            discount_amount=item.discount_amount,
            tax_amount=item.tax_amount,
            remaining_line_total=item.line_total - line_r,
            remaining_discount=item.discount_amount - disc_r,
            remaining_tax=item.tax_amount - tax_r,
        ))

    blocked = _blocked_reason(sale, actor.store_id, window)
    if blocked is None and not any(ln.qty_returnable > 0 for ln in lines):
        blocked = "Everything on this bill has already been returned."
    return ReturnableBillOut(
        sale_id=sale.id,
        bill_number=sale.bill_number,
        completed_at=sale.completed_at,
        cashier_name=sale.cashier.full_name,
        total=sale.total,
        payment_methods=sorted({p.method for p in sale.payments}, key=lambda m: m.value),
        days_left=max(window - _days_since(sale.completed_at), 0),
        can_return=blocked is None,
        blocked_reason=blocked,
        lines=lines,
    )


def bills_for_mobile(mobile: str, actor: User) -> list[BillForMobileOut]:
    """A customer's recent paid bills, for returns when the receipt is lost. Own store only (head office: all)."""
    number = normalize_mobile(mobile)
    if number is None:
        return []
    return [
        BillForMobileOut(
            bill_number=s.bill_number,
            completed_at=s.completed_at,
            total=s.total,
            items_count=len(s.items),
        )
        for s in SaleRepository().paid_by_mobile(number, actor.store_id)
    ]


def create_return(data: CreateReturnRequest, actor: User) -> SaleReturn:
    approver = billing_service._verify_approver(data.approver_username, data.approver_pin, "a return")
    shift = require_active_shift(actor.id)
    window = settings_service.get_settings().return_window_days

    with transaction():
        # Lock the bill so two returns on the same bill can't both take the last units.
        sale = _paid_sale(data.bill_number, for_update=True)
        blocked = _blocked_reason(sale, shift.store_id, window)
        if blocked:
            raise AppError(blocked)

        done = ReturnRepository().returned_by_item(sale.id)
        items = {i.id: i for i in sale.items}
        seen: set[int] = set()
        ret = SaleReturn(
            sale_id=sale.id,
            store_id=sale.store_id,
            shift_id=shift.id,
            cashier_id=actor.id,
            approved_by_id=approver.id,
            reason=data.reason.strip(),
            refund_method=PaymentMethod.CASH,
        )
        for ln in data.lines:
            item = items.get(ln.sale_item_id)
            if item is None:
                raise AppError(f"Line {ln.sale_item_id} is not on bill {sale.bill_number}.")
            if item.id in seen:
                raise AppError(f"{item.product_name} is listed twice.")
            seen.add(item.id)
            if ln.qty % 1 != 0 and not _is_weighed(item):
                raise AppError(f"{item.product_name}: return whole units only.")

            qty_r, line_r, disc_r, tax_r = done.get(item.id, NOTHING_RETURNED)
            remaining = item.qty - qty_r
            if ln.qty > remaining:
                raise AppError(
                    f"{item.product_name}: only {_qty_text(remaining)} can be returned "
                    f"(sold {_qty_text(item.qty)}, already returned {_qty_text(qty_r)})."
                )
            line, disc, tax = _share(item, ln.qty, remaining, line_r, disc_r, tax_r)
            ret.items.append(SaleReturnItem(
                sale_item_id=item.id,
                product_id=item.product_id,
                product_name=item.product_name,
                hsn_code=item.hsn_code,
                tax_rate=item.tax_rate,
                qty=ln.qty,
                line_total=line,
                discount_amount=disc,
                tax_amount=tax,
                refund_amount=line - disc + tax,
                restocked=ln.restock,
            ))

        ret.subtotal = sum((i.line_total for i in ret.items), ZERO)
        ret.discount_amount = sum((i.discount_amount for i in ret.items), ZERO)
        ret.tax_amount = sum((i.tax_amount for i in ret.items), ZERO)
        ret.refund_amount = sum((i.refund_amount for i in ret.items), ZERO)

        db.session.add(ret)
        db.session.flush()
        ret.return_number = f"RT{sale.store_id:02d}-{now_ist():%y%m%d}-{ret.id:05d}"

        inventory_service.restock_for_return(
            sale.store_id,
            [i for i in ret.items if i.restocked],
            ret.id,
            f"Return {ret.return_number} of bill {sale.bill_number}",
        )
        audit_service.log(
            actor, "sale.return", "sale", sale.id, None,
            {
                "return_number": ret.return_number,
                "refund": str(ret.refund_amount),
                "method": ret.refund_method.value,
                "approved_by": approver.username,
                "reason": ret.reason,
            },
        )
    return ret


def get_return(return_id: int) -> SaleReturn:
    ret = ReturnRepository().get_by_id(return_id)
    if ret is None:
        raise NotFoundError(f"Return {return_id} not found.")
    return ret


def to_out(ret: SaleReturn) -> ReturnOut:
    sale = ret.sale
    return ReturnOut(
        id=ret.id,
        return_number=ret.return_number,
        created_at=ret.created_at,
        sale_id=sale.id,
        bill_number=sale.bill_number,
        bill_date=sale.completed_at,
        store_name=ret.store.name,
        store_address=ret.store.address,
        store_phone=ret.store.phone,
        store_gstin=ret.store.gstin,
        counter_code=sale.counter.code if sale.counter else None,
        cashier_name=ret.cashier.full_name,
        customer_mobile=mask_mobile(sale.customer_mobile),
        approved_by_name=ret.approved_by.full_name,
        reason=ret.reason,
        refund_method=ret.refund_method,
        subtotal=ret.subtotal,
        discount_amount=ret.discount_amount,
        tax_amount=ret.tax_amount,
        refund_amount=ret.refund_amount,
        items=[ReturnItemOut.model_validate(i) for i in ret.items],
        gst_summary=[GstSummaryRow(**row) for row in pricing_service.gst_summary(ret.items)],
        receipt_footer=settings_service.get_settings().receipt_footer,
    )


def _paid_sale(bill_number: str, for_update: bool = False) -> Sale:
    number = bill_number.strip()
    sale = SaleRepository().get_by_bill_number(number, for_update=for_update)
    if sale is None or sale.status is not SaleStatus.PAID:
        raise NotFoundError(f"No paid bill with number '{number}'.")
    return sale


def _share(item: SaleItem, qty, remaining, line_r, disc_r, tax_r) -> tuple[Decimal, Decimal, Decimal]:
    """The returned part of a bill line, in proportion to qty, so offers and discounts are reversed
    fairly. Returning the last units takes exactly what is left, so all returns add up to the line."""
    if qty == remaining:
        return item.line_total - line_r, item.discount_amount - disc_r, item.tax_amount - tax_r
    ratio = qty / item.qty
    return (
        round_money(item.line_total * ratio),
        round_money(item.discount_amount * ratio),
        round_money(item.tax_amount * ratio),
    )


def _blocked_reason(sale: Sale, store_id: int | None, window: int) -> str | None:
    """Why this bill can't be returned here and now, or None. store_id None = head-office user (any store)."""
    if store_id is not None and store_id != sale.store_id:
        return "This bill is from another store. Return it at the store where it was bought."
    days = _days_since(sale.completed_at)
    if days > window:
        return f"This bill is {days} days old. Returns are accepted within {window} days."
    return None


def _is_weighed(item: SaleItem) -> bool:
    return bool(item.product and item.product.is_variable_weight)


def _days_since(when: datetime) -> int:
    return (now_ist().date() - when.astimezone(IST).date()).days


def _qty_text(q) -> str:
    return f"{Decimal(str(q)).normalize():f}"
