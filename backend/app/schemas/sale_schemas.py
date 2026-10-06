"""Sale, sale item and complete-sale schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


from app.models.enums import SaleStatus
from app.schemas.payment_schemas import PaymentOut


class SaleItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    tax_rate: Decimal
    qty: int | float
    line_total: Decimal
    discount_amount: Decimal
    tax_amount: Decimal

    model_config = {"from_attributes": True}

    @field_validator("qty", mode="before")
    @classmethod
    def coerce_qty(cls, v: Any) -> int | float:
        if v is None:
            return 0
        d = Decimal(str(v))
        if d % 1 == 0:
            return int(d)
        return float(d)



class SaleOut(BaseModel):
    id: int
    bill_number: str | None
    store_id: int
    counter_id: int | None
    shift_id: int
    cashier_id: int
    status: SaleStatus
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    note: str | None
    items: list[SaleItemOut]
    payments: list[PaymentOut]
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AddItemRequest(BaseModel):
    product_id: int = Field(..., ge=1)
    qty: Decimal = Field(Decimal("1"), ge=Decimal("0.001"), le=Decimal("9999"))


class UpdateItemRequest(BaseModel):
    qty: Decimal = Field(..., ge=Decimal("0.001"), le=Decimal("9999"))



class HoldSaleRequest(BaseModel):
    note: str | None = Field(None, max_length=255)


class CompleteSaleRequest(BaseModel):
    method: Literal["cash", "card", "upi"]
    cash_tendered: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    reference: str | None = Field(None, max_length=100)


class ReceiptOut(BaseModel):
    sale_id: int
    bill_number: str
    store_name: str
    store_address: str | None
    store_phone: str | None
    store_gstin: str | None
    counter_code: str | None
    cashier_name: str
    completed_at: datetime
    items: list[SaleItemOut]
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    payments: list[PaymentOut]
    receipt_header: str
    receipt_footer: str
