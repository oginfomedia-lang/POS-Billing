"""Builds receipt data (JSON) for printing and reprinting. Does not print."""
from __future__ import annotations

from app.errors.exceptions import ConflictError
from app.models.enums import SaleStatus
from app.schemas.payment_schemas import PaymentOut
from app.schemas.sale_schemas import EbillStatusOut, GstSummaryRow, ReceiptOut, SaleItemOut
from app.services import ebill_service, pricing_service, settings_service
from app.utils.phone import mask_mobile
from app.services.billing_service import get_sale


def build_receipt(sale_id: int) -> ReceiptOut:
    sale = get_sale(sale_id)
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
        customer_mobile=mask_mobile(sale.customer_mobile),
        completed_at=sale.completed_at,
        items=[SaleItemOut.model_validate(i) for i in sale.items],
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
        ebill=EbillStatusOut(**ebill) if (ebill := ebill_service.status_for_sale(sale.id)) else None,
    )
