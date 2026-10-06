"""Product, category, and barcode schemas."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, field_validator


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
    is_primary: bool


class ProductOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    description: str | None
    category_id: int | None
    price: Decimal
    tax_rate: Decimal
    is_active: bool
    store_id: int | None
    barcodes: list[BarcodeOut] = []


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    category_id: int | None = None
    price: Decimal
    tax_rate: Decimal = Decimal("0")
    store_id: int | None = None
    barcodes: list[str] = []

    @field_validator("price", "tax_rate", mode="before")
    @classmethod
    def coerce_decimal(cls, v):
        return Decimal(str(v))


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category_id: int | None = None
    price: Decimal | None = None
    tax_rate: Decimal | None = None
    is_active: bool | None = None
    store_id: int | None = None


class ProductBarcodeOut(BaseModel):
    model_config = {"from_attributes": True}

    product: ProductOut
    qty_on_hand: Decimal | None = None
