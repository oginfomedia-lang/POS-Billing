"""Sale, sale item and complete-sale schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


from app.models.enums import SaleStatus
from app.schemas.payment_schemas import PaymentOut


class SaleItemOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    unit_price: Decimal
    tax_rate: Decimal
    mrp: Decimal | None = None  # incl. GST, per unit
    hsn_code: str | None = None
    qty: int | float
    line_total: Decimal
    discount_amount: Decimal
    offer_name: str | None = None
    offer_discount: Decimal = Decimal("0")
    manual_discount: Decimal = Decimal("0")
    manual_discount_reason: str | None = None
    reward_discount: Decimal = Decimal("0")  # this line's share of the reward points discount
    tax_amount: Decimal
    saving: Decimal = Decimal("0")  # MRP × qty − paid (or the discount when there is no MRP)
    is_variable_weight: bool = False  # loose item: qty is a weight (kg)
    uom: str = "pcs"

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
    bill_offer_name: str | None = None
    bill_offer_discount: Decimal = Decimal("0")
    tax_amount: Decimal
    total: Decimal
    total_saving: Decimal = Decimal("0")
    note: str | None
    customer_mobile: str | None = None
    points_redeemed: int = 0  # reserved while the bill is open, used once it's paid
    reward_discount: Decimal = Decimal("0")  # ₹ off for those points (before GST, inside discount_amount)
    points_earned: int = 0
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


class ManualDiscountRequest(BaseModel):
    """Counter discount on one line (e.g. damaged pack). amount 0 removes it.
    A manager or admin approves it by typing their own username and PIN."""

    amount: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    reason: str = Field("", max_length=100)
    approver_username: str = Field(..., min_length=1, max_length=50)
    approver_pin: str = Field(..., min_length=4, max_length=8)

    @model_validator(mode="after")
    def need_reason(self) -> "ManualDiscountRequest":
        if self.amount > 0 and not self.reason.strip():
            raise ValueError("Enter a reason for the discount.")
        return self



class HoldSaleRequest(BaseModel):
    note: str | None = Field(None, max_length=255)


class CustomerMobileRequest(BaseModel):
    mobile: str | None = Field(None, max_length=20)  # null / "" clears it


class CompleteSaleRequest(BaseModel):
    method: Literal["cash", "card", "upi"]
    cash_tendered: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    reference: str | None = Field(None, max_length=100)
    payment_intent_id: int | None = None   # required for card/upi: proof Razorpay confirmed the money


class GstSummaryRow(BaseModel):
    """One line of the rate-wise GST table on a receipt / credit note."""

    tax_rate: Decimal
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    tax: Decimal


class EbillStatusOut(BaseModel):
    """Latest WhatsApp e-bill for a bill (shown on the bill screen, never printed)."""

    status: str  # pending / sent / failed
    recipient: str  # masked, e.g. 98XXXXX210
    error: str | None = None
    sent_at: datetime | None = None


class EbillSendRequest(BaseModel):
    """Send on WhatsApp: to this number, or the bill's customer mobile when empty."""

    mobile: str | None = Field(None, max_length=20)


class ReceiptOut(BaseModel):
    sale_id: int
    bill_number: str
    store_name: str
    store_address: str | None
    store_phone: str | None
    store_gstin: str | None
    counter_code: str | None
    cashier_name: str
    customer_mobile: str | None = None  # masked, e.g. 98XXXXX210
    completed_at: datetime
    items: list[SaleItemOut]
    subtotal: Decimal
    discount_amount: Decimal
    bill_offer_name: str | None = None
    bill_offer_discount: Decimal = Decimal("0")
    tax_amount: Decimal
    total: Decimal
    total_saving: Decimal = Decimal("0")
    points_redeemed: int = 0
    reward_discount: Decimal = Decimal("0")
    points_earned: int = 0
    points_balance: int | None = None  # customer's balance now (None = no customer on the bill)
    gst_summary: list[GstSummaryRow] = []
    payments: list[PaymentOut]
    receipt_header: str
    receipt_footer: str
    receipt_footer_mr: str = ""
    fssai_number: str = ""
    ebill: EbillStatusOut | None = None
