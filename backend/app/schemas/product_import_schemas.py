"""Bulk product import (CSV / Excel): options, the row-by-row check (preview) and the result."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ImportOptions(BaseModel):
    # Store that gets the opening stock; with sold_in="store" also the only store selling the new products.
    store_id: int | None = None
    sold_in: Literal["all", "store"] = "all"
    # New packet products with no barcode get one of our own (290...) so stickers can be printed.
    generate_barcodes: bool = True


class ImportRowOut(BaseModel):
    row: int  # row number as shown in Excel (header = row 1)
    name: str
    action: Literal["create", "update", "error"]
    product_id: int | None = None  # the existing product an "update" row changes
    errors: list[str] = []
    warnings: list[str] = []


class ImportPreview(BaseModel):
    total: int
    creates: int
    updates: int
    errors: int
    new_categories: list[str] = []
    warnings: list[str] = []  # about the file as a whole, e.g. unknown columns
    rows: list[ImportRowOut]


class GeneratedBarcode(BaseModel):
    product_id: int
    name: str
    barcode: str


class ImportResult(BaseModel):
    created: int
    updated: int
    opening_stock_rows: int
    new_categories: list[str] = []
    generated_barcodes: list[GeneratedBarcode] = []
