"""Product, category, and barcode schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator, ValidationInfo

from app.models.enums import BarcodeType


class CategoryOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    parent_id: int | None
    is_active: bool


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None


class CategoryUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None


class BarcodeOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    barcode: str
    barcode_type: BarcodeType
    is_primary: bool
    created_at: datetime


class BarcodeCreatePayload(BaseModel):
    barcode: str
    barcode_type: BarcodeType = BarcodeType.MANUFACTURER
    is_primary: bool = False


class ProductOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    sku: str
    name: str
    description: str | None
    category_id: int | None
    price: Decimal
    tax_rate: Decimal
    is_variable_weight: bool
    is_active: bool
    store_id: int | None
    barcodes: list[BarcodeOut] = []


class ProductCreate(BaseModel):
    name: str
    sku: str | None = None
    description: str | None = None
    category_id: int | None = None
    price: Decimal
    tax_rate: Decimal = Decimal("0")
    is_variable_weight: bool = False
    store_id: int | None = None
    barcodes: list[str | BarcodeCreatePayload] = []

    @field_validator("price", "tax_rate", mode="before")
    @classmethod
    def coerce_decimal(cls, v: str | int | float | Decimal | None, info: ValidationInfo) -> Decimal:
        if v is None:
            return Decimal("0")
        return Decimal(str(v))


class ProductUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    description: str | None = None
    category_id: int | None = None
    price: Decimal | None = None
    tax_rate: Decimal | None = None
    is_variable_weight: bool | None = None
    is_active: bool | None = None
    store_id: int | None = None
    barcodes: list[str | BarcodeCreatePayload] | None = None

    @field_validator("price", "tax_rate", mode="before")
    @classmethod
    def coerce_decimal_optional(cls, v: str | int | float | Decimal | None, info: ValidationInfo) -> Decimal | None:
        if v is None:
            return None
        return Decimal(str(v))


class ProductBarcodeOut(BaseModel):
    model_config = {"from_attributes": True}

    product: ProductOut
    qty_on_hand: Decimal | None = None
    scanned_barcode: str | None = None
    is_variable_weight: bool = False
    weight_grams: int | None = None
    weight_kg: float | None = None
    unit_price: Decimal | None = None
    calculated_price: Decimal | None = None
