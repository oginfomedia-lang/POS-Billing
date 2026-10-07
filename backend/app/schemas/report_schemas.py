"""Report filter and result schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, model_validator

from app.models.enums import PaymentMethod

MAX_RANGE_DAYS = 366


class ReportQuery(BaseModel):
    """Dates are inclusive business dates (IST). Omitted dates default to today."""

    store_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def check_range(self) -> "ReportQuery":
        if self.date_from and self.date_to:
            if self.date_to < self.date_from:
                raise ValueError("date_to must be on or after date_from.")
            if (self.date_to - self.date_from).days >= MAX_RANGE_DAYS:
                raise ValueError(f"Choose a range of at most {MAX_RANGE_DAYS} days.")
        return self


class SalesSummary(BaseModel):
    bills: int
    voided: int
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    average_bill: Decimal


class MethodRow(BaseModel):
    method: PaymentMethod
    bills: int
    amount: Decimal


class DailyRow(BaseModel):
    day: date
    bills: int
    total: Decimal


class GstRow(BaseModel):
    tax_rate: Decimal
    taxable: Decimal
    tax: Decimal
    cgst: Decimal  # intra-state split: half CGST, half SGST
    sgst: Decimal


class TopProductRow(BaseModel):
    product_id: int
    product_name: str
    qty: int
    amount: Decimal


class OfferRow(BaseModel):
    kind: Literal["item", "bill", "manual"]
    name: str
    bills: int  # bills the offer was used on
    amount: Decimal  # rupees given away (before GST)


class SalesReportOut(BaseModel):
    store_id: int | None
    date_from: date
    date_to: date
    summary: SalesSummary
    by_method: list[MethodRow]
    daily: list[DailyRow]
    gst: list[GstRow]
    top_products: list[TopProductRow]
    offers: list[OfferRow]


class ShiftRow(BaseModel):
    id: int
    cashier_name: str
    counter_code: str | None
    status: str
    opened_at: datetime
    closed_at: datetime | None
    opening_float: Decimal
    bills: int
    cash_sales: Decimal
    expected_cash: Decimal | None
    actual_cash: Decimal | None
    difference: Decimal | None  # actual - expected; negative = cash short


class RecentSale(BaseModel):
    id: int
    bill_number: str
    cashier_name: str
    total: Decimal
    completed_at: datetime


class DashboardOut(BaseModel):
    store_id: int | None
    date: date
    summary: SalesSummary
    by_method: list[MethodRow]
    open_shifts: int
    low_stock: int
    recent_sales: list[RecentSale]
