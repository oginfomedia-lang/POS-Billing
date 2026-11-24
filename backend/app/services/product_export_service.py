"""Products to a file people open in Excel: .xlsx (default) or .csv.

The columns are the import template's (product_import_service.COLUMNS), in the same order, so a shop can export,
change prices or GST in Excel and import the same file back: a row whose SKU is already saved updates that product.
Three columns for reading only come after them (price with GST, this store's own price, active); the import skips
them with a note.
"""
from __future__ import annotations

import csv
import io
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.product import Product
from app.repositories.product_repository import search_filter
from app.services import inventory_service
from app.services.product_import_service import COLUMNS, TEXT_COLUMNS

EXTRA_COLUMNS = ["price_with_gst", "store_price", "active"]
HEADER = COLUMNS + EXTRA_COLUMNS
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# Text Excel would run as a formula when the CSV is opened (a product name typed as "=HYPERLINK(...)").
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def export_products(*, fmt: str, store_id: int | None, search: str | None, is_active: bool | None,
                    with_cost: bool) -> tuple[bytes, str, str]:
    """(file, mimetype, file name) with every product the Products page lists for these filters: all pages,
    not only the 25 on screen. Purchase cost only when with_cost (admin / manager)."""
    rows = _rows(store_id, search, is_active, with_cost)
    stamp = date.today().isoformat()
    if fmt == "csv":
        return _csv(rows), "text/csv; charset=utf-8", f"products-{stamp}.csv"
    return _xlsx(rows), XLSX_MIME, f"products-{stamp}.xlsx"


def _rows(store_id: int | None, search: str | None, is_active: bool | None, with_cost: bool) -> list[list]:
    # Same filters as ProductRepository.list (the Products page), without paging. selectinload: category,
    # supplier and barcode come in 3 queries for all products, not 3 per product.
    q = (db.select(Product)
         .options(selectinload(Product.category), selectinload(Product.supplier), selectinload(Product.barcodes))
         .order_by(Product.name))
    if is_active is not None:
        q = q.where(Product.is_active.is_(is_active))
    if search and search.strip():
        q = q.where(search_filter(search.strip()))
    if store_id is not None:
        q = q.where((Product.store_id == store_id) | (Product.store_id.is_(None)))
    products = db.session.scalars(q).all()
    own_prices = inventory_service.store_prices(store_id, [p.id for p in products]) if store_id else {}

    out = []
    for p in products:
        barcode = next((b for b in p.barcodes if b.is_primary), None) or next(iter(p.barcodes), None)
        values = {
            "name": p.name,
            "price": p.price,  # before GST, as saved and as the import reads it
            "tax_rate": p.tax_rate,
            "mrp": p.mrp,
            "hsn_code": p.hsn_code,
            "uom": p.uom.value,
            "category": p.category.name if p.category else None,
            "sku": p.sku,  # the import finds the product again by it
            "barcodes": barcode.barcode if barcode else None,
            "is_variable_weight": "yes" if p.is_variable_weight else "no",
            "plu_code": p.plu_code,
            "supplier_code": p.supplier.supplier_code if p.supplier else None,
            "opening_stock": None,  # the import uses these two for new products only: left empty
            "expiry_date": None,
            "cost_price": p.cost_price if with_cost else None,
            "price_with_gst": (p.price * (1 + p.tax_rate / 100)).quantize(Decimal("0.01"), ROUND_HALF_UP),
            "store_price": own_prices.get(p.id),
            "active": "yes" if p.is_active else "no",
        }
        out.append([values[c] for c in HEADER])
    return out


def _xlsx(rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(HEADER)
    for i, cell in enumerate(ws[1]):
        cell.font = Font(bold=True)
        # Import columns blue like the template; the 3 read-only columns grey.
        cell.fill = PatternFill("solid", fgColor="E0E7FF" if i < len(COLUMNS) else "E5E7EB")
    for r, row in enumerate(rows, start=2):
        for c, value in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=value)
            if isinstance(value, str):
                cell.data_type = "s"  # always text, never a formula (a name starting with "=")
            if HEADER[c - 1] in TEXT_COLUMNS:
                cell.number_format = "@"  # barcodes, HSN: all digits shown, leading zeros kept
    for i, col in enumerate(HEADER, start=1):
        letter = ws.cell(row=1, column=i).column_letter
        ws.column_dimensions[letter].width = 30 if col == "name" else 16
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _csv(rows: list[list]) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(HEADER)
    for row in rows:
        writer.writerow(["'" + v if isinstance(v, str) and v.startswith(_FORMULA_START) else v for v in row])
    # BOM: Excel then reads Marathi names and ₹ as UTF-8 (the import reads it too, utf-8-sig).
    return ("\ufeff" + out.getvalue()).encode("utf-8")
