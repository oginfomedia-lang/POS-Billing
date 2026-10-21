"""Shift open/close schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ShiftOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    store_id: int
    counter_id: int | None
    status: str
    opening_float: Decimal
    expected_cash: Decimal | None
    actual_cash: Decimal | None
    opened_at: datetime
    closed_at: datetime | None


class OpenShiftRequest(BaseModel):
    opening_float: Decimal = Decimal("0")
    store_id: int
    counter_id: int | None = None


class CloseShiftRequest(BaseModel):
    actual_cash: Decimal


class ShiftBillPaymentOut(BaseModel):
    method: str
    amount: Decimal


class ShiftBillOut(BaseModel):
    """One bill on the cashier's shift list."""

    id: int
    bill_number: str | None  # held / voided drafts have none
    status: str  # paid / held / voided
    completed_at: datetime | None
    created_at: datetime
    total: Decimal
    items_count: int
    payments: list[ShiftBillPaymentOut]
    customer_mobile: str | None  # masked
    return_count: int = 0
    refunded: Decimal = Decimal("0.00")  # given back on this bill so far (any shift)


class ShiftReturnOut(BaseModel):
    """A refund paid out of this shift's drawer (the bill may be from another shift)."""

    id: int
    return_number: str | None
    bill_number: str | None
    created_at: datetime
    refund_method: str
    refund_amount: Decimal


class ShiftSummaryOut(BaseModel):
    """The same numbers close_shift uses: expected cash = opening float + cash sales − cash refunds."""

    paid_bills: int
    held_bills: int  # still on hold: not paid, not in the drawer
    voided_bills: int  # cancelled before payment (empty drafts not counted)
    sales_total: Decimal  # all paid bills, every payment method
    cash_sales: Decimal
    card_sales: Decimal
    upi_sales: Decimal
    returns: int
    cash_refunds: Decimal
    other_refunds: Decimal
    opening_float: Decimal
    expected_cash: Decimal  # what should be in the drawer now (card / UPI excluded)


class ShiftBillsOut(BaseModel):
    shift: ShiftOut
    cashier_name: str
    counter_code: str | None
    summary: ShiftSummaryOut
    bills: list[ShiftBillOut]
    returns: list[ShiftReturnOut]
