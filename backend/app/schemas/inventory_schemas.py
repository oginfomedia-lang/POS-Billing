"""Inventory and stock movement schemas."""
from __future__ import annotations

from datetime import datetime
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
    created_at: datetime

    model_config = {"from_attributes": True}
