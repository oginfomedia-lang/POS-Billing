"""Inventory and stock movement schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import InventoryTxnType, UOMType


class StockLevelOut(BaseModel):
    product_id: int
    product_name: str
    barcode: str | None
    qty_on_hand: Decimal  # the whole stock: shop + godown
    shop_qty: Decimal = Decimal("0")  # on the shop shelf
    godown_qty: Decimal = Decimal("0")  # in the godown
    shelf_min_qty: Decimal | None = None  # refill the shelf at this level; None = no shelf alert
    needs_refill: bool = False  # shelf at / below shelf_min_qty and the godown has some
    uom: UOMType = UOMType.PCS
    low_stock_threshold: Decimal | None  # this product's own level; None = use the Settings default
    effective_threshold: Decimal
    is_low: bool  # the WHOLE stock is low: time to order from the supplier
    base_price: Decimal  # head-office price (products.price)
    store_price: Decimal | None  # this store's own price; None = sells at base_price
    price: Decimal  # what this store actually charges (before GST)


class TransferRequest(BaseModel):
    """Move goods between the godown and the shop shelf."""

    store_id: int
    product_id: int
    qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    direction: Literal["to_shop", "to_godown"] = "to_shop"
    notes: str | None = Field(None, max_length=255)


class ShelfMinRequest(BaseModel):
    store_id: int
    product_id: int
    shelf_min_qty: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=3)


class RefillOut(BaseModel):
    """A product whose shelf is running low while the godown still has some."""

    product_id: int
    product_name: str
    uom: UOMType
    shop_qty: Decimal
    godown_qty: Decimal
    shelf_min_qty: Decimal


class StockTransferOut(BaseModel):
    id: int
    product_id: int
    product_name: str
    qty: Decimal
    direction: str
    reason: str
    reference_id: int | None
    user_name: str | None
    notes: str | None
    created_at: datetime



class ThresholdRequest(BaseModel):
    store_id: int
    product_id: int
    threshold: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=3)


class StorePriceRequest(BaseModel):
    """This store's own selling price (before GST). None = go back to the head-office price."""

    store_id: int
    product_id: int
    price: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)


class StockInRequest(BaseModel):
    store_id: int
    product_id: int
    qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    notes: str | None = Field(None, max_length=500)
    expiry_date: date | None = None
    batch_number: str | None = Field(None, max_length=100)
    to_godown: bool = False  # True = the goods went into the godown, not on the shelf


class AdjustStockRequest(BaseModel):
    """Set the counted quantity (stock-take, damage, theft). A reason is required.

    location: what was counted. None = the whole stock (as before); "shop" / "godown" = only that place,
    the other place keeps its figure."""

    store_id: int
    product_id: int
    new_qty: Decimal = Field(..., ge=0, max_digits=12, decimal_places=3)
    notes: str = Field(..., min_length=1, max_length=500)
    location: Literal["shop", "godown"] | None = None


class InventoryTxnOut(BaseModel):
    id: int
    product_id: int
    txn_type: InventoryTxnType
    qty: Decimal
    reference_id: int | None
    notes: str | None
    expiry_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExpiringBatchOut(BaseModel):
    """One batch expiring soon (or already expired: days_to_expiry < 0)."""
    product_id: int
    product_name: str
    barcode: str | None
    qty_on_hand: Decimal  # the product's whole stock in this store
    uom: UOMType
    nearest_expiry: date  # this batch's expiry date
    days_to_expiry: int
    batch_id: int | None = None
    batch_number: str | None = None
    batch_qty: Decimal | None = None  # what is left of this batch
    batch_source: str | None = None  # grn = came from a supplier, so it can be sent back


class BatchOut(BaseModel):
    id: int
    batch_number: str | None
    mfg_date: date | None
    expiry_date: date | None
    qty_received: Decimal
    qty_remaining: Decimal
    source: str  # grn / stock_in / opening / return / adjustment / migration
    received_at: datetime
    days_to_expiry: int | None


class BatchWriteOffRequest(BaseModel):
    """Expired or damaged goods of one batch leave stock. qty omitted = everything left in the batch."""
    qty: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=3)
    reason: str = Field(..., min_length=1, max_length=200)
    from_godown: bool = False  # True = the spoilt goods are in the godown (rats, leaking cartons)


class BatchReturnRequest(BaseModel):
    """Goods of one GRN batch go back to the supplier who sent them; the supplier owes us their value.
    qty omitted = everything left in the batch."""
    qty: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=3)
    reason: str = Field(..., min_length=1, max_length=200)
    from_godown: bool = False


class SupplierReturnOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    return_number: str
    supplier_id: int
    supplier_name: str = ""
    product_id: int
    product_name: str = ""
    batch_id: int
    goods_receipt_id: int
    receipt_number: str = ""
    qty: Decimal
    amount: Decimal
    reason: str
    # How much of the amount went against the GRN's invoice; the rest is credit with the supplier
    applied_to_invoice: Decimal = Decimal("0")
    created_at: datetime
