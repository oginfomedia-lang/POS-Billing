"""Inventory and stock movement schemas."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import InventoryTxnType, UOMType


class StockLevelOut(BaseModel):
    product_id: int
    product_name: str
    barcode: str | None
    qty_on_hand: Decimal
    uom: UOMType = UOMType.PCS
    low_stock_threshold: Decimal | None  # this product's own level; None = use the Settings default
    effective_threshold: Decimal
    is_low: bool
    base_price: Decimal  # head-office price (products.price)
    store_price: Decimal | None  # this store's own price; None = sells at base_price
    price: Decimal  # what this store actually charges (before GST)



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


class AdjustStockRequest(BaseModel):
    """Set the counted quantity (stock-take, damage, theft). A reason is required."""

    store_id: int
    product_id: int
    new_qty: Decimal = Field(..., ge=0, max_digits=12, decimal_places=3)
    notes: str = Field(..., min_length=1, max_length=500)


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
