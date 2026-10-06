"""Builds receipt data (JSON) for printing and reprinting. Does not print."""
from __future__ import annotations

from app.errors.exceptions import ConflictError
from app.models.enums import SaleStatus
from app.schemas.payment_schemas import PaymentOut
from app.schemas.sale_schemas import ReceiptOut, SaleItemOut
from app.services.billing_service import get_sale


def build_receipt(sale_id: int) -> ReceiptOut:
    sale = get_sale(sale_id)
    if sale.status is not SaleStatus.PAID:
        raise ConflictError("A receipt is only available for completed bills.")

    return ReceiptOut(
        sale_id=sale.id,
        bill_number=sale.bill_number,
        store_name=sale.store.name,
        store_address=sale.store.address,
        store_phone=sale.store.phone,
        store_gstin=sale.store.gstin,
        counter_code=sale.counter.code,
        cashier_name=sale.cashier.full_name,
        completed_at=sale.completed_at,
        items=[SaleItemOut.model_validate(i) for i in sale.items],
        subtotal=sale.subtotal,
        discount_amount=sale.discount_amount,
        tax_amount=sale.tax_amount,
        total=sale.total,
        payments=[PaymentOut.model_validate(p) for p in sale.payments],
    )
