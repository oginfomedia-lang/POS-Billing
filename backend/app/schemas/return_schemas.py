"""Return (credit note) schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.models.enums import PaymentMethod
from app.schemas.sale_schemas import GstSummaryRow


def _qty_out(v: Any) -> int | float:
    d = Decimal(str(v or 0))
    return int(d) if d % 1 == 0 else float(d)


class ReturnLineIn(BaseModel):
    sale_item_id: int
    qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    restock: bool = True  # False = damaged; don't put it back in stock


class CreateReturnRequest(BaseModel):
    bill_number: str = Field(..., min_length=1, max_length=40)
    lines: list[ReturnLineIn] = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=255)
    approver_username: str = Field(..., min_length=1, max_length=50)
    approver_pin: str = Field(..., min_length=1, max_length=20)


class ReturnableLineOut(BaseModel):
    sale_item_id: int
    product_id: int
    product_name: str
    hsn_code: str | None
    unit_price: Decimal
    tax_rate: Decimal
    is_variable_weight: bool  # weighed items can be returned in fractions (kg)
    qty_sold: int | float
    qty_returned: int | float
    qty_returnable: int | float
    # The original line, and what is still left of it after earlier returns, so the screen can
    # preview the refund with the same proportional maths as the server.
    line_total: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    remaining_line_total: Decimal
    remaining_discount: Decimal
    remaining_tax: Decimal

    @field_validator("qty_sold", "qty_returned", "qty_returnable", mode="before")
    @classmethod
    def _qty(cls, v: Any) -> int | float:
        return _qty_out(v)


class ReturnableBillOut(BaseModel):
    sale_id: int
    bill_number: str
    completed_at: datetime
    cashier_name: str
    total: Decimal
    payment_methods: list[PaymentMethod]
    days_left: int  # days left in the return window (0 = last day)
    can_return: bool
    blocked_reason: str | None  # why can_return is False
    lines: list[ReturnableLineOut]


class BillForMobileOut(BaseModel):
    """One of a customer's paid bills, found by mobile number."""

    bill_number: str
    completed_at: datetime
    total: Decimal
    items_count: int


class ReturnItemOut(BaseModel):
    product_name: str
    hsn_code: str | None
    tax_rate: Decimal
    qty: int | float
    line_total: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    refund_amount: Decimal
    restocked: bool

    model_config = {"from_attributes": True}

    @field_validator("qty", mode="before")
    @classmethod
    def _qty(cls, v: Any) -> int | float:
        return _qty_out(v)


class ReturnOut(BaseModel):
    """A credit note: everything needed to show and print the return slip."""

    id: int
    return_number: str
    created_at: datetime
    sale_id: int
    bill_number: str
    bill_date: datetime
    store_name: str
    store_address: str | None
    store_phone: str | None
    store_gstin: str | None
    counter_code: str | None
    cashier_name: str
    customer_mobile: str | None = None  # masked
    approved_by_name: str
    reason: str
    refund_method: PaymentMethod
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    refund_amount: Decimal
    items: list[ReturnItemOut]
    gst_summary: list[GstSummaryRow]
    receipt_footer: str
    receipt_footer_mr: str = ""
