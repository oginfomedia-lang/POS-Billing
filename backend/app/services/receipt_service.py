"""Builds receipt data (JSON) for printing and reprinting. Does not print."""
from __future__ import annotations

from decimal import Decimal

from app.errors.exceptions import ConflictError
from app.models.enums import SaleStatus
from app.schemas.payment_schemas import PaymentOut
from app.schemas.sale_schemas import EbillStatusOut, GstSummaryRow, ReceiptOut, SaleItemOut
from app.services import ebill_service, pricing_service, settings_service
from app.models.user import User
from app.services.billing_service import get_sale
from app.utils.store_scope import require_same_store_or_404


def total_qty(items) -> Decimal:
    """Sum of the bill lines' quantities, exact (Decimal): 2 + 3 + 1.25 = 6.25. Shown without trailing
    zeros: "10", "23.5", "1.235"."""
    total = sum((Decimal(str(i.qty)) for i in items), Decimal("0")).quantize(Decimal("0.001"))
    return total.quantize(Decimal("1")) if total == total.to_integral_value() else total.normalize()


def build_receipt(sale_id: int, actor: User | None = None) -> ReceiptOut:
    """actor: the person asking (staff only see their own store's bills). None = internal use (e-bill PDF)."""
    sale = get_sale(sale_id)
    if actor is not None:
        require_same_store_or_404(actor, sale.store_id, f"Sale {sale_id}")
    if sale.status is not SaleStatus.PAID:
        raise ConflictError("A receipt is only available for completed bills.")
    settings = settings_service.get_settings()

    return ReceiptOut(
        sale_id=sale.id,
        bill_number=sale.bill_number,
        store_name=sale.store.name,
        store_address=sale.store.address,
        store_phone=sale.store.phone,
        store_gstin=sale.store.gstin,
        counter_code=sale.counter.code if sale.counter else None,
        cashier_name=sale.cashier.full_name,
        customer_mobile=sale.customer_mobile,
        completed_at=sale.completed_at,
        items=[SaleItemOut.model_validate(i) for i in sale.items],
        item_lines=len(sale.items),
        total_qty=total_qty(sale.items),
        subtotal=sale.subtotal,
        discount_amount=sale.discount_amount,
        bill_offer_name=sale.bill_offer_name,
        bill_offer_discount=sale.bill_offer_discount,
        tax_amount=sale.tax_amount,
        total=sale.total,
        total_saving=sale.total_saving,
        points_redeemed=sale.points_redeemed,
        reward_discount=sale.reward_discount,
        points_earned=sale.points_earned,
        points_balance=sale.customer.points_balance if sale.customer else None,
        gst_summary=[GstSummaryRow(**row) for row in pricing_service.gst_summary(sale.items)],
        payments=[PaymentOut.model_validate(p) for p in sale.payments],
        receipt_header=settings.receipt_header,
        receipt_footer=settings.receipt_footer,
        receipt_footer_mr=settings.receipt_footer_mr,
        fssai_number=settings.fssai_number,
        ebill=EbillStatusOut(**ebill) if (ebill := ebill_service.status_for_sale(sale.id)) else None,
    )
