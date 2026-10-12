"""Schemas for Purchase Management module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import PurchaseStatus


class PurchaseOrderItemCreate(BaseModel):
    product_id: int
    ordered_qty: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    unit_price: Decimal = Field(..., ge=0, max_digits=12, decimal_places=2)
    discount_percent: Decimal = Field(Decimal("0"), ge=0, le=100, max_digits=5, decimal_places=2)
    tax_rate: Decimal = Field(Decimal("0"), ge=0, max_digits=5, decimal_places=2)


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    store_id: int | None = None
    purchase_date: date
    expected_delivery_date: date | None = None
    reference_number: str | None = Field(None, max_length=100)
    notes: str | None = None
    internal_remarks: str | None = None
    items: list[PurchaseOrderItemCreate] = Field(..., min_length=1)


class PurchaseOrderUpdate(BaseModel):
    supplier_id: int | None = None
    store_id: int | None = None
    purchase_date: date | None = None
    expected_delivery_date: date | None = None
    reference_number: str | None = Field(None, max_length=100)
    notes: str | None = None
    internal_remarks: str | None = None
    items: list[PurchaseOrderItemCreate] | None = None


class PurchaseOrderItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    product_id: int
    product_name: str
    product_sku: str | None
    ordered_qty: Decimal
    received_qty: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    tax_rate: Decimal
    line_discount: Decimal
    tax_amount: Decimal
    line_total: Decimal


class PurchaseOrderOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    po_number: str
    supplier_id: int
    supplier_name: str = ""
    store_id: int | None
    purchase_date: date
    expected_delivery_date: date | None
    reference_number: str | None
    notes: str | None
    internal_remarks: str | None
    subtotal: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    grand_total: Decimal
    status: PurchaseStatus
    ordered_at: datetime | None
    cancelled_at: datetime | None
    created_by_id: int | None
    created_by_name: str = ""
    items: list[PurchaseOrderItemOut] = []
    created_at: datetime
    updated_at: datetime


class GoodsReceiptItemCreate(BaseModel):
    purchase_order_item_id: int
    qty_received: Decimal = Field(..., gt=0, max_digits=12, decimal_places=3)
    expiry_date: date | None = None


class GoodsReceiptCreate(BaseModel):
    received_at: datetime | None = None
    notes: str | None = None
    items: list[GoodsReceiptItemCreate] = Field(..., min_length=1)


class GoodsReceiptItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    purchase_order_item_id: int
    product_id: int
    product_name: str = ""
    qty_received: Decimal
    expiry_date: date | None


class GoodsReceiptOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    purchase_order_id: int
    receipt_number: str
    received_at: datetime
    received_by_id: int | None
    received_by_name: str = ""
    notes: str | None
    receipt_items: list[GoodsReceiptItemOut] = []
    created_at: datetime


class PurchaseDashboard(BaseModel):
    total: int
    total_value: Decimal
    pending: int
    ordered: int
    partially_received: int
    received: int
    cancelled: int
