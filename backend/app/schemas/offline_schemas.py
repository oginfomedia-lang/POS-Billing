"""Offline billing: the catalogue a counter keeps for when the server is unreachable, and the bills it uploads."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import DiscountScope, DiscountType, UOMType
from app.schemas.sale_schemas import MAX_LINE_QTY


class OfflineProduct(BaseModel):
    id: int
    name: str
    sku: str
    barcode: str | None
    plu_code: str | None
    category_id: int | None
    price: Decimal  # this store's selling price, before GST
    tax_rate: Decimal
    mrp: Decimal | None
    hsn_code: str | None
    uom: UOMType
    is_variable_weight: bool


class OfflineOffer(BaseModel):
    """An offer, with the fields discount_service.choose_best_offer uses. The counter checks the dates itself."""
    id: int
    name: str
    discount_type: DiscountType
    value: Decimal
    scope: DiscountScope
    product_id: int | None
    category_id: int | None
    min_bill_amount: Decimal | None
    max_discount_amount: Decimal | None
    buy_qty: int | None
    get_qty: int | None
    starts_at: datetime | None
    ends_at: datetime | None


class OfflineStore(BaseModel):
    """What the receipt header needs."""
    id: int
    name: str
    address: str | None
    phone: str | None
    gstin: str | None


class OfflineSettings(BaseModel):
    scale_prefix: str
    scale_plu_digits: int
    scale_value: Literal["weight", "price"]
    receipt_header: str
    receipt_footer: str
    receipt_footer_mr: str
    fssai_number: str


class OfflineCatalogOut(BaseModel):
    generated_at: datetime
    store: OfflineStore
    settings: OfflineSettings
    products: list[OfflineProduct]
    offers: list[OfflineOffer]
    categories: dict[int, int | None]  # {category_id: parent_id}, for category offers on sub-categories


class OfflineSaleItemIn(BaseModel):
    product_id: int
    product_name: str = Field(..., max_length=200)
    qty: Decimal = Field(..., ge=Decimal("0.001"), le=MAX_LINE_QTY)
    unit_price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    tax_rate: Decimal = Field(..., ge=0, le=100)
    mrp: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    hsn_code: str | None = Field(None, max_length=8)
    # All of the discount on this line (item offer or its share of the bill offer), before GST.
    discount_amount: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    offer_id: int | None = None
    offer_name: str | None = Field(None, max_length=100)
    offer_discount: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)


class OfflineSaleIn(BaseModel):
    """A cash bill made on a counter while the server was unreachable. Amounts are what the customer paid;
    the server checks the arithmetic, it does not re-price."""
    offline_id: str = Field(..., min_length=8, max_length=36, pattern=r"^[A-Za-z0-9-]+$")
    bill_number: str = Field(..., max_length=40, pattern=r"^[A-Z0-9]{1,10}-OFF-\d{6}-\d{4,6}$")
    shift_id: int
    billed_at: datetime
    items: list[OfflineSaleItemIn] = Field(..., min_length=1, max_length=500)
    bill_offer_id: int | None = None
    bill_offer_name: str | None = Field(None, max_length=100)
    bill_offer_discount: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    total: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    cash_tendered: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
