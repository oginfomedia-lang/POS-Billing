"""Review selling prices: rows, and setting a price."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class PriceReviewRow(BaseModel):
    product_id: int
    name: str
    sku: str | None
    category_name: str | None
    uom: str | None
    cost_price: Decimal  # latest rate paid, before GST
    tax_rate: Decimal
    mrp: Decimal | None  # incl. GST
    price: Decimal  # current selling price, before GST
    price_incl: Decimal  # with GST
    margin_percent: Decimal | None  # profit on cost at the current price
    below_cost: bool  # selling at a loss
    target_percent: Decimal
    suggested_price: Decimal  # before GST
    suggested_price_incl: Decimal
    suggested_margin_percent: Decimal | None
    capped_at_mrp: bool  # the MRP doesn't allow the target profit
    details_pending: bool = False  # new product typed on a PO: no selling price yet
    above_mrp: bool = False  # current price with GST is above the MRP (e.g. a lower MRP came on new stock)


class PriceReviewOut(BaseModel):
    items: list[PriceReviewRow]
    default_margin_percent: Decimal


class ApplyPriceRequest(BaseModel):
    price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)  # before GST
