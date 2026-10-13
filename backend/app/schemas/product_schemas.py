"""Product, category, and barcode schemas."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator, ValidationInfo

from app.models.enums import BarcodeType, UOMType


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


def _optional_decimal(v):
    """"" or None = no value (e.g. a blank MRP box)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return Decimal(str(v))


def _optional_hsn(v):
    """HSN codes are 4, 6 or 8 digits. "" or None = no HSN."""
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    if not re.fullmatch(r"\d{4,8}", v):
        raise ValueError("HSN code must be 4 to 8 digits.")
    return v


def _optional_plu(v):
    """Weighing-scale item code: 1-6 digits, stored without leading zeros. "" or None = no code."""
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    if not re.fullmatch(r"\d{1,6}", v):
        raise ValueError("Scale item code must be 1 to 6 digits.")
    return str(int(v))


class ProductOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    sku: str
    name: str
    description: str | None
    category_id: int | None
    price: Decimal
    tax_rate: Decimal
    mrp: Decimal | None = None
    hsn_code: str | None = None
    uom: UOMType = UOMType.PCS
    is_variable_weight: bool
    plu_code: str | None = None
    is_active: bool
    store_id: int | None
    supplier_id: int | None = None
    barcodes: list[BarcodeOut] = []
    # Only when the request names a store: that store's own selling price (None = sells at `price`).
    store_price: Decimal | None = None


class ProductCreate(BaseModel):
    name: str
    sku: str | None = None
    description: str | None = None
    category_id: int | None = None
    price: Decimal
    tax_rate: Decimal = Decimal("0")
    mrp: Decimal | None = None  # incl. GST
    hsn_code: str | None = None
    uom: UOMType = UOMType.PCS
    is_variable_weight: bool = False
    plu_code: str | None = None  # loose items only: the item code set on the weighing scale
    store_id: int | None = None
    supplier_id: int | None = None  # usual supplier (for information; any supplier can be used on a PO)
    barcodes: list[str | BarcodeCreatePayload] = []

    @field_validator("price", "tax_rate", mode="before")
    @classmethod
    def coerce_decimal(cls, v: str | int | float | Decimal | None, info: ValidationInfo) -> Decimal:
        if v is None:
            return Decimal("0")
        return Decimal(str(v))

    _mrp = field_validator("mrp", mode="before")(classmethod(lambda cls, v: _optional_decimal(v)))
    _hsn = field_validator("hsn_code", mode="before")(classmethod(lambda cls, v: _optional_hsn(v)))
    _plu = field_validator("plu_code", mode="before")(classmethod(lambda cls, v: _optional_plu(v)))


class ProductUpdate(BaseModel):
    name: str | None = None
    sku: str | None = None
    description: str | None = None
    category_id: int | None = None
    price: Decimal | None = None
    tax_rate: Decimal | None = None
    # mrp / hsn_code: leave out to keep the saved value; send null or "" to clear it.
    mrp: Decimal | None = None
    hsn_code: str | None = None
    uom: UOMType | None = None
    is_variable_weight: bool | None = None
    # Leave out to keep; send null or "" to clear.
    plu_code: str | None = None
    is_active: bool | None = None
    store_id: int | None = None
    # Leave out to keep; null removes the supplier.
    supplier_id: int | None = None
    barcodes: list[str | BarcodeCreatePayload] | None = None

    _mrp = field_validator("mrp", mode="before")(classmethod(lambda cls, v: _optional_decimal(v)))
    _hsn = field_validator("hsn_code", mode="before")(classmethod(lambda cls, v: _optional_hsn(v)))
    _plu = field_validator("plu_code", mode="before")(classmethod(lambda cls, v: _optional_plu(v)))

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
