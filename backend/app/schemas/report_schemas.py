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
    returns: int = 0  # credit notes in the period
    refunded: Decimal = Decimal("0")  # cash given back for returns (incl. GST)
    net_total: Decimal = Decimal("0")  # total - refunded


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


class GstHsnRow(BaseModel):
    hsn_code: str | None  # None = products without an HSN code
    tax_rate: Decimal
    taxable: Decimal
    tax: Decimal
    cgst: Decimal
    sgst: Decimal


class TopProductRow(BaseModel):
    product_id: int
    product_name: str
    qty: Decimal  # loose items sold by weight have fractions (2.5 kg)
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
    gst_hsn: list[GstHsnRow] = []
    top_products: list[TopProductRow]
    offers: list[OfferRow]


class ProfitSummary(BaseModel):
    net_sales: Decimal  # all sales after returns, before GST
    returns: Decimal  # returned goods (before GST), already taken out of net_sales
    costed_sales: Decimal  # the part of net_sales whose cost is known
    cogs: Decimal  # cost of goods sold
    gross_profit: Decimal  # costed_sales - cogs
    margin_pct: Decimal | None  # gross_profit / costed_sales
    uncosted_sales: Decimal  # sales of items with no cost price: not in profit
    uncosted_products: int


class ProfitRow(BaseModel):
    product_id: int
    product_name: str
    category: str | None
    qty: Decimal
    net_sales: Decimal
    cogs: Decimal
    gross_profit: Decimal
    margin_pct: Decimal | None


class ProfitCategoryRow(BaseModel):
    category: str | None  # None = no category
    net_sales: Decimal
    cogs: Decimal
    gross_profit: Decimal
    margin_pct: Decimal | None


class UncostedRow(BaseModel):
    product_id: int
    product_name: str
    qty: Decimal
    net_sales: Decimal


class ProfitReportOut(BaseModel):
    store_id: int | None
    date_from: date
    date_to: date
    summary: ProfitSummary
    by_category: list[ProfitCategoryRow]
    products: list[ProfitRow]  # highest profit first; losses (sold below cost) at the end
    uncosted: list[UncostedRow]


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
    cash_refunds: Decimal = Decimal("0")
    expected_cash: Decimal | None
    actual_cash: Decimal | None
    difference: Decimal | None  # actual - expected; negative = cash short


class CollectionRow(BaseModel):
    """What one cashier collected on one counter."""

    cashier_id: int
    cashier_name: str
    counter_code: str | None
    bills: int = 0
    cash: Decimal = Decimal("0.00")
    card: Decimal = Decimal("0.00")
    upi: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")  # cash + card + upi
    refunds: Decimal = Decimal("0.00")  # cash given back for returns
    net: Decimal = Decimal("0.00")  # total - refunds
    cash_difference: Decimal | None = None  # counted - expected on shifts closed in the period; negative = short
    shift_open: bool = False  # a shift is still open, so the numbers may still change


class CollectionTotals(BaseModel):
    bills: int
    cash: Decimal
    card: Decimal
    upi: Decimal
    total: Decimal
    refunds: Decimal
    net: Decimal


class CollectionReportOut(BaseModel):
    store_id: int | None
    date_from: date
    date_to: date
    rows: list[CollectionRow]
    totals: CollectionTotals


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
    # products with stock whose batch expires within 30 days (Stock / Inventory → Expiry alerts)
    near_expiry: int = 0
    recent_sales: list[RecentSale]


# ── Bill and return lists (where the dashboard / report tiles lead) ──────────────────

class BillListQuery(ReportQuery):
    """Same dates and store as the sales report, so the list adds up to its tiles."""

    status: Literal["paid", "voided"] = "paid"
    method: PaymentMethod | None = None  # bills with a payment of this kind
    discounted: bool = False  # only bills with a discount
    q: str | None = None  # part of the bill number
    page: int = 1
    per_page: int = 50

    @model_validator(mode="after")
    def _paging(self) -> "BillListQuery":
        self.page = max(self.page, 1)
        self.per_page = min(max(self.per_page, 1), 200)
        return self


class BillRow(BaseModel):
    id: int
    bill_number: str | None
    status: str
    at: datetime  # paid at (completed_at), or cancelled at for a voided bill
    cashier_name: str
    counter_code: str | None
    items_count: int
    customer_mobile: str | None  # masked
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    methods: list[PaymentMethod]
    refunded: Decimal = Decimal("0")


class ListTotals(BaseModel):
    count: int
    subtotal: Decimal = Decimal("0")
    discount: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    total: Decimal = Decimal("0")


class BillListOut(BaseModel):
    date_from: date
    date_to: date
    items: list[BillRow]
    totals: ListTotals  # of every bill matching the filters, not just this page
    page: int
    per_page: int
    pages: int


class ReturnListRow(BaseModel):
    id: int
    return_number: str | None
    created_at: datetime
    bill_number: str | None
    sale_id: int
    cashier_name: str
    approved_by_name: str
    reason: str
    refund_method: PaymentMethod
    refund_amount: Decimal
    items_count: int


class ReturnListOut(BaseModel):
    date_from: date
    date_to: date
    items: list[ReturnListRow]
    totals: ListTotals  # count and total refunded
    page: int
    per_page: int
    pages: int
