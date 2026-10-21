"""Product, category, and barcode schemas."""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel, field_validator, ValidationInfo

from app.models.enums import BarcodeType, UOMType


class CategoryOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    parent_id: int | None
    is_active: bool


def _category_name(v: str | None) -> str | None:
    if v is None:
        return v
    v = " ".join(v.split())
    if not v:
        raise ValueError("Enter a category name.")
    if len(v) > 100:
        raise ValueError("Category name can be at most 100 characters.")
    return v


class CategoryCreate(BaseModel):
    name: str
    parent_id: int | None = None

    _name = field_validator("name")(_category_name)


class CategoryUpdate(BaseModel):
    """Only the fields sent are changed; "parent_id": null moves the category to the top level."""
    name: str | None = None
    parent_id: int | None = None
    is_active: bool | None = None

    _name = field_validator("name")(_category_name)


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


# Largest values the columns hold: NUMERIC(12, 2) money, NUMERIC(12, 4) cost, a GST rate up to 100 %.
MAX_MONEY = Decimal("9999999999.99")
MAX_COST = Decimal("99999999.9999")


def _number(v, label: str) -> Decimal:
    """A number from the form / API, or a clear 422 (not a server error) for text like "abc"."""
    try:
        value = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a number.") from None
    if not value.is_finite():
        raise ValueError(f"{label} must be a number.")
    return value


def _price(v):
    """Selling price before GST: 0 (free item) up to the largest amount a bill can hold. Never negative:
    a negative price makes a bill with a negative amount and discount."""
    value = _number(v, "Selling price")
    if value < 0:
        raise ValueError("Selling price can't be negative.")
    if value > MAX_MONEY:
        raise ValueError(f"Selling price can be at most {MAX_MONEY}.")
    return value


def _tax_rate(v):
    value = _number(v, "GST rate")
    if not Decimal("0") <= value <= Decimal("100"):
        raise ValueError("GST rate must be between 0 and 100 %.")
    return value


def _optional_decimal(v):
    """"" or None = no value (e.g. a blank MRP box)."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return _number(v, "Value")


def _optional_mrp(v):
    value = _optional_decimal(v)
    if value is not None and not Decimal("0") <= value <= MAX_MONEY:
        raise ValueError(f"MRP must be between 0 and {MAX_MONEY}.")
    return value


def _optional_cost(v):
    """Blank = no cost. A cost can't be negative."""
    value = _optional_decimal(v)
    if value is not None and value < 0:
        raise ValueError("Cost price can't be negative.")
    if value is not None and value > MAX_COST:
        raise ValueError(f"Cost price can be at most {MAX_COST}.")
    return value


def _product_name(v):
    """Trimmed, not blank, fits the column (200)."""
    if v is None:
        return v
    v = " ".join(str(v).split())
    if not v:
        raise ValueError("Enter a product name.")
    if len(v) > 200:
        raise ValueError("Product name can be at most 200 characters.")
    return v


def _one_barcode(v):
    """A product has at most one barcode."""
    if v is not None and len([b for b in v if (b if isinstance(b, str) else b.barcode).strip()]) > 1:
        raise ValueError("A product can have only one barcode.")
    return v


def _optional_text(limit: int, label: str):
    def check(v):
        if v is None:
            return v
        v = str(v).strip()
        if len(v) > limit:
            raise ValueError(f"{label} can be at most {limit} characters.")
        return v or None
    return check


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
    # Admin / manager only (filled in by the product routes, never from the model): default cost before GST, and
    # the selected store's weighted-average cost from goods receipts.
    cost_price: Decimal | None = None
    store_avg_cost: Decimal | None = None

    @field_validator("cost_price", mode="before")
    @classmethod
    def _hide_cost(cls, v):
        return None  # see the comment above: the route sets it after validation for admin / manager


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
    cost_price: Decimal | None = None  # purchase cost before GST (admin / manager; ignored for others)

    _barcodes = field_validator("barcodes")(classmethod(lambda cls, v: _one_barcode(v)))

    @field_validator("price", mode="before")
    @classmethod
    def coerce_price(cls, v: str | int | float | Decimal | None, info: ValidationInfo) -> Decimal:
        return _price(0 if v is None else v)

    @field_validator("tax_rate", mode="before")
    @classmethod
    def coerce_tax(cls, v: str | int | float | Decimal | None, info: ValidationInfo) -> Decimal:
        return _tax_rate(0 if v is None else v)

    _name = field_validator("name", mode="before")(classmethod(lambda cls, v: _product_name(v)))
    _sku = field_validator("sku", mode="before")(classmethod(lambda cls, v: _optional_text(50, "SKU")(v)))
    _mrp = field_validator("mrp", mode="before")(classmethod(lambda cls, v: _optional_mrp(v)))
    _hsn = field_validator("hsn_code", mode="before")(classmethod(lambda cls, v: _optional_hsn(v)))
    _plu = field_validator("plu_code", mode="before")(classmethod(lambda cls, v: _optional_plu(v)))
    _cost = field_validator("cost_price", mode="before")(classmethod(lambda cls, v: _optional_cost(v)))


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
    # Leave out to keep; null or "" clears. Admin / manager only (ignored for others).
    cost_price: Decimal | None = None

    _barcodes = field_validator("barcodes")(classmethod(lambda cls, v: _one_barcode(v)))

    _name = field_validator("name", mode="before")(classmethod(lambda cls, v: _product_name(v)))
    _sku = field_validator("sku", mode="before")(classmethod(lambda cls, v: _optional_text(50, "SKU")(v)))
    _mrp = field_validator("mrp", mode="before")(classmethod(lambda cls, v: _optional_mrp(v)))
    _hsn = field_validator("hsn_code", mode="before")(classmethod(lambda cls, v: _optional_hsn(v)))
    _plu = field_validator("plu_code", mode="before")(classmethod(lambda cls, v: _optional_plu(v)))
    _cost = field_validator("cost_price", mode="before")(classmethod(lambda cls, v: _optional_cost(v)))

    @field_validator("price", mode="before")
    @classmethod
    def coerce_price_optional(cls, v: str | int | float | Decimal | None, info: ValidationInfo) -> Decimal | None:
        return None if v is None else _price(v)

    @field_validator("tax_rate", mode="before")
    @classmethod
    def coerce_tax_optional(cls, v: str | int | float | Decimal | None, info: ValidationInfo) -> Decimal | None:
        return None if v is None else _tax_rate(v)


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
