"""Bulk product import from a CSV or Excel file.

Two steps, both from the same uploaded file:
1. analyse(): reads every row and decides create / update / error. Nothing is saved (the preview screen).
2. apply(): only when no row has an error, saves everything in one transaction (all or nothing).

A row whose SKU or barcode is already in the system updates that product (price, MRP, GST...); blank cells
keep what is saved, and a barcode is only added to a product that has none (one per product). Opening stock is for new products only, so
importing a price list again never doubles the stock. It is written to the stock ledger like any stock-in.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from app.errors.exceptions import BadRequestError
from app.extensions import db
from app.models.category import Category
from app.models.enums import BarcodeType, InventoryTxnType, UOMType
from app.models.product import Product, ProductBarcode
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.product_import_schemas import (
    GeneratedBarcode,
    ImportOptions,
    ImportPreview,
    ImportResult,
    ImportRowOut,
)
from app.schemas.product_schemas import MAX_COST, MAX_MONEY, _optional_hsn, _optional_plu
from app.services import audit_service, batch_service
from app.services.product_service import (
    _add_barcode_to_product,
    _infer_barcode_type,
    link_supplier,
    mrp_error,
    next_inhouse_barcode,
)
from app.utils.permissions import has_permission
from app.utils.store_scope import is_head_office, require_store_access
from app.utils.transactions import transaction

MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024
OPENING_STOCK_NOTE = "Opening stock (bulk import)"

COLUMNS = [
    "name", "price", "tax_rate", "mrp", "hsn_code", "uom", "category", "sku", "barcodes",
    "is_variable_weight", "plu_code", "supplier_code", "opening_stock", "expiry_date", "cost_price",
]
# Other headings people commonly use for the same thing.
ALIASES = {
    "product": "name", "product_name": "name", "item": "name", "item_name": "name",
    "selling_price": "price", "rate": "price", "sale_price": "price",
    "gst": "tax_rate", "gst_rate": "tax_rate", "tax": "tax_rate",
    "hsn": "hsn_code",
    "unit": "uom",
    "barcode": "barcodes", "ean": "barcodes",
    "loose": "is_variable_weight", "loose_item": "is_variable_weight", "variable_weight": "is_variable_weight",
    "weighed": "is_variable_weight",
    "plu": "plu_code", "scale_code": "plu_code",
    "supplier": "supplier_code",
    "stock": "opening_stock", "qty": "opening_stock", "quantity": "opening_stock",
    "expiry": "expiry_date",
    "cost": "cost_price", "purchase_price": "cost_price", "purchase_rate": "cost_price", "cost_rate": "cost_price",
}
UOM_ALIASES = {
    "pc": "pcs", "piece": "pcs", "pieces": "pcs", "nos": "pcs", "no": "pcs", "unit": "pcs",
    "kgs": "kg", "kilo": "kg", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "l": "ltr", "litre": "ltr", "liter": "ltr", "lit": "ltr", "packet": "pack", "pkt": "pack",
}
YES = {"yes", "y", "true", "1", "हो", "होय"}
NO = {"no", "n", "false", "0", "नाही"}
DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y")
SCIENTIFIC = re.compile(r"^\d+(\.\d+)?e\+?\d+$", re.IGNORECASE)


# ── Reading the file ──────────────────────────────────────────────────────────

def _header(text) -> str:
    key = re.sub(r"[^a-z0-9]+", "_", str(text or "").strip().lower()).strip("_")
    return ALIASES.get(key, key)


def read_rows(filename: str, data: bytes) -> tuple[list[tuple[int, dict]], list[str]]:
    """[(excel row number, {column: cell})] plus warnings about the file. Raises on an unusable file."""
    if not data:
        raise BadRequestError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise BadRequestError("The file is too big (max 5 MB). Split it into smaller files.")
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        table = _xlsx_rows(data)
    elif name.endswith(".csv"):
        table = _csv_rows(data)
    elif name.endswith(".xls"):
        raise BadRequestError("Old .xls files aren't supported. In Excel use File → Save As → Excel Workbook (.xlsx).")
    else:
        raise BadRequestError("Upload a .csv or .xlsx file.")

    header_at = next((i for i, (_, cells) in enumerate(table) if any(_text(c) for c in cells)), None)
    if header_at is None:
        raise BadRequestError("The file has no rows.")
    header_row, header_cells = table[header_at]
    headers = [_header(h) for h in header_cells]
    if "name" not in headers and "sku" not in headers and "barcodes" not in headers:
        raise BadRequestError(
            f"Row {header_row} must be the column headings (name, price, ...). Download the template to see them."
        )
    warnings = []
    unknown = sorted({h for h in headers if h and h not in COLUMNS})
    if unknown:
        warnings.append(f"These columns are ignored: {', '.join(unknown)}.")

    rows = []
    for number, cells in table[header_at + 1:]:
        values = {h: cells[i] if i < len(cells) else None for i, h in enumerate(headers) if h in COLUMNS}
        if any(_text(v) for v in values.values()):
            rows.append((number, values))
    if not rows:
        raise BadRequestError("The file has headings but no products.")
    if len(rows) > MAX_ROWS:
        raise BadRequestError(f"Too many rows ({len(rows)}). Import at most {MAX_ROWS} products at a time.")
    return rows, warnings


def _xlsx_rows(data: bytes) -> list[tuple[int, list]]:
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - any parse failure is the same message to the user
        raise BadRequestError("Couldn't read this Excel file. Save it again as .xlsx and retry.") from exc
    try:
        ws = wb.worksheets[0]
        return [(i, list(r)) for i, r in enumerate(ws.iter_rows(values_only=True), start=1)]
    finally:
        wb.close()


def _csv_rows(data: bytes) -> list[tuple[int, list]]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1252 decodes almost anything
        raise BadRequestError("Couldn't read this CSV file. In Excel save it as 'CSV UTF-8'.")
    return [(i, r) for i, r in enumerate(csv.reader(io.StringIO(text)), start=1)]


def _text(value) -> str:
    """A cell as text: whole numbers without '.0' (barcodes keep every digit), dates as YYYY-MM-DD."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else format(Decimal(str(value)), "f")
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip()


# ── Checking each row ─────────────────────────────────────────────────────────

@dataclass
class _Row:
    number: int
    name: str = ""
    values: dict = field(default_factory=dict)  # typed values for the columns that were filled in
    barcodes: list[str] = field(default_factory=list)
    match: Product | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def action(self) -> str:
        return "error" if self.errors else ("update" if self.match else "create")


def _parse(number: int, cells: dict) -> _Row:
    row = _Row(number)
    raw = {k: _text(v) for k, v in cells.items()}
    row.name = raw.get("name", "")[:200]
    if row.name:
        row.values["name"] = row.name

    for col in ("price", "tax_rate", "mrp", "cost_price"):
        text = raw.get(col, "").replace("₹", "").replace(",", "").rstrip("%").strip()
        if not text:
            continue
        try:
            value = Decimal(text)
        except InvalidOperation:
            row.errors.append(f"{col}: '{raw[col]}' is not a number.")
            continue
        limit = Decimal("100") if col == "tax_rate" else MAX_COST if col == "cost_price" else MAX_MONEY
        if value < 0 or value > limit:
            row.errors.append(f"{col}: {value} is out of range (0 to {limit}).")
            continue
        row.values[col] = value.quantize(Decimal("0.01"))

    if raw.get("hsn_code"):
        try:
            row.values["hsn_code"] = _optional_hsn(raw["hsn_code"])
        except ValueError as exc:
            row.errors.append(str(exc))

    if raw.get("uom"):
        uom = UOM_ALIASES.get(raw["uom"].lower(), raw["uom"].lower())
        if uom in {u.value for u in UOMType}:
            row.values["uom"] = UOMType(uom)
        else:
            row.errors.append(f"uom: '{raw['uom']}' — use pcs, kg, g, ltr, ml or pack.")

    if raw.get("category"):
        row.values["category"] = raw["category"][:100]

    for col in ("sku", "barcodes", "plu_code"):
        if SCIENTIFIC.match(raw.get(col, "").replace(" ", "")):
            row.errors.append(
                f"{col}: '{raw[col]}' was changed by Excel into a short number. "
                "Format the column as Text, type the full number again, and save."
            )
            raw[col] = ""
    if raw.get("sku"):
        if len(raw["sku"]) > 50:
            row.errors.append("sku: longer than 50 characters.")
        else:
            row.values["sku"] = raw["sku"]
    if raw.get("barcodes"):
        row.barcodes = list(dict.fromkeys(b for b in re.split(r"[|,;\s]+", raw["barcodes"]) if b))
        for b in row.barcodes:
            if len(b) > 100:
                row.errors.append(f"barcode '{b[:20]}…' is too long.")
        if len(row.barcodes) > 1:
            row.errors.append("barcodes: a product can have only one barcode.")

    if raw.get("is_variable_weight"):
        flag = raw["is_variable_weight"].lower()
        if flag in YES or flag in NO:
            row.values["is_variable_weight"] = flag in YES
        else:
            row.errors.append(f"is_variable_weight: '{raw['is_variable_weight']}' — use yes or no.")
    if raw.get("plu_code"):
        try:
            row.values["plu_code"] = _optional_plu(raw["plu_code"])
        except ValueError as exc:
            row.errors.append(str(exc))

    if raw.get("supplier_code"):
        row.values["supplier_code"] = raw["supplier_code"].upper()

    stock = raw.get("opening_stock", "").replace(",", "")
    if stock:
        try:
            qty = Decimal(stock)
            if qty < 0 or qty > Decimal("99999999"):
                raise InvalidOperation
            row.values["opening_stock"] = qty.quantize(Decimal("0.001"))
        except InvalidOperation:
            row.errors.append(f"opening_stock: '{raw['opening_stock']}' is not a valid quantity.")

    expiry = cells.get("expiry_date")
    if isinstance(expiry, (datetime, date)):
        row.values["expiry_date"] = expiry.date() if isinstance(expiry, datetime) else expiry
    elif raw.get("expiry_date"):
        for fmt in DATE_FORMATS:
            try:
                row.values["expiry_date"] = datetime.strptime(raw["expiry_date"], fmt).date()
                break
            except ValueError:
                continue
        else:
            row.errors.append(f"expiry_date: '{raw['expiry_date']}' — use DD-MM-YYYY.")
    return row


@dataclass
class _Lookups:
    """Everything a row is checked against, loaded once for the whole file."""
    by_sku: dict[str, Product]
    by_barcode: dict[str, int]
    by_plu: dict[str, int]
    products: dict[int, Product]
    suppliers: dict[str, Supplier]
    categories: dict[str, Category]

    @classmethod
    def load(cls) -> "_Lookups":
        products = {p.id: p for p in db.session.scalars(db.select(Product))}
        return cls(
            by_sku={p.sku: p for p in products.values()},
            by_barcode=dict(db.session.execute(db.select(ProductBarcode.barcode, ProductBarcode.product_id)).all()),
            by_plu={p.plu_code: p.id for p in products.values() if p.plu_code},
            products=products,
            suppliers={s.supplier_code.upper(): s for s in db.session.scalars(db.select(Supplier))},
            categories={c.name.strip().lower(): c for c in db.session.scalars(db.select(Category))},
        )


def analyse(rows: list[tuple[int, dict]], options: ImportOptions, actor: User) -> tuple[ImportPreview, list[_Row]]:
    """Checks every row; saves nothing."""
    store_error = _check_options(options, actor)
    look = _Lookups.load()
    parsed = [_parse(n, cells) for n, cells in rows]
    seen_sku: dict[str, int] = {}
    seen_barcode: dict[str, int] = {}
    seen_plu: dict[str, int] = {}
    seen_product: dict[int, int] = {}
    new_categories: dict[str, str] = {}

    for row in parsed:
        v = row.values
        # Which existing product (if any) is this row about?
        by_sku = look.by_sku.get(v["sku"]) if "sku" in v else None
        by_barcode = {look.by_barcode[b] for b in row.barcodes if b in look.by_barcode}
        if by_sku and by_barcode - {by_sku.id}:
            other = look.products[next(iter(by_barcode - {by_sku.id}))]
            row.errors.append(f"SKU belongs to '{by_sku.name}' but a barcode belongs to '{other.name}'.")
        elif not by_sku and len(by_barcode) > 1:
            names = ", ".join(f"'{look.products[i].name}'" for i in sorted(by_barcode))
            row.errors.append(f"The barcodes belong to different products: {names}.")
        elif "sku" in v and not by_sku and by_barcode:
            other = look.products[next(iter(by_barcode))]
            row.errors.append(f"The barcode belongs to '{other.name}' (SKU {other.sku}), not to SKU {v['sku']}.")
        else:
            row.match = by_sku or (look.products[next(iter(by_barcode))] if by_barcode else None)

        # The same SKU / barcode / scale code / product twice in the file.
        for key, seen, label in [(v.get("sku"), seen_sku, "SKU")] + [(b, seen_barcode, "Barcode") for b in row.barcodes] \
                + [(v.get("plu_code"), seen_plu, "Scale code")]:
            if key and key in seen:
                row.errors.append(f"{label} {key} is also on row {seen[key]}.")
            elif key:
                seen[key] = row.number
        if row.match is not None:
            if row.match.id in seen_product:
                row.errors.append(f"Same product as row {seen_product[row.match.id]}.")
            seen_product.setdefault(row.match.id, row.number)
            if not row.name:
                row.name = row.match.name
            saved = [b.barcode for b in row.match.barcodes]
            if row.barcodes and saved and row.barcodes[0] not in saved:
                row.errors.append(
                    f"'{row.match.name}' already has barcode {saved[0]}; a product can have only one barcode."
                )

        _check_row(row, look, options, actor, store_error, new_categories)

    out_rows = [
        ImportRowOut(
            row=r.number, name=r.name or "—", action=r.action,
            product_id=r.match.id if r.match is not None else None, errors=r.errors, warnings=r.warnings,
        )
        for r in parsed
    ]
    preview = ImportPreview(
        total=len(parsed),
        creates=sum(r.action == "create" for r in parsed),
        updates=sum(r.action == "update" for r in parsed),
        errors=sum(r.action == "error" for r in parsed),
        new_categories=sorted(new_categories.values(), key=str.lower),
        rows=out_rows,
    )
    return preview, parsed


def _check_options(options: ImportOptions, actor: User) -> str | None:
    """Problems with the store choice; reported on the rows that need a store."""
    if options.store_id is None:
        return "Choose the store for opening stock / store-only products on the import screen."
    store = db.session.get(Store, options.store_id)
    if store is None or not store.is_active:
        raise BadRequestError("Choose an active store.")
    require_store_access(actor, options.store_id)
    return None


def _check_row(row: _Row, look: _Lookups, options: ImportOptions, actor: User, store_error, new_categories) -> None:
    v = row.values
    p = row.match
    if p is None:
        if not row.name:
            row.errors.append("name is required for a new product.")
        if "price" not in v:
            row.errors.append("price is required for a new product.")
        if options.sold_in == "store" and store_error:
            row.errors.append(store_error)
    elif p.store_id is not None and not is_head_office(actor) and p.store_id != actor.store_id:
        row.errors.append(f"'{p.name}' belongs to another store.")

    # The product as it will be after this row.
    price = v.get("price", p.price if p else None)
    tax_rate = v.get("tax_rate", p.tax_rate if p else Decimal("0"))
    mrp = v.get("mrp", p.mrp if p else None)
    loose = v.get("is_variable_weight", p.is_variable_weight if p else False)
    plu = v.get("plu_code", p.plu_code if p else None)
    if price is not None and (err := mrp_error(price, tax_rate, mrp)):
        row.errors.append(err)
    if plu and not loose:
        row.errors.append("plu_code is only for loose items (is_variable_weight = yes).")
    if plu and look.by_plu.get(plu) not in (None, p.id if p else None):
        row.errors.append(f"Scale code {plu} is already used by '{look.products[look.by_plu[plu]].name}'.")

    if "supplier_code" in v:
        supplier = look.suppliers.get(v["supplier_code"])
        if supplier is None:
            row.errors.append(f"Supplier code {v['supplier_code']} not found (see the Suppliers page).")
        elif not supplier.is_active:
            row.errors.append(f"Supplier {v['supplier_code']} is inactive.")
    if "category" in v and v["category"].strip().lower() not in look.categories:
        new_categories.setdefault(v["category"].strip().lower(), v["category"].strip())

    if "opening_stock" in v:
        if p is not None:
            row.warnings.append("Opening stock ignored: this product already exists. Use Stock in or a purchase order.")
        elif store_error:
            row.errors.append(store_error)
        elif not loose and v["opening_stock"] != v["opening_stock"].to_integral_value():
            row.errors.append("opening_stock must be a whole number for packet items.")
    if "expiry_date" in v and "opening_stock" not in v:
        row.warnings.append("expiry_date is ignored without opening_stock.")

    if p is None and not row.barcodes:
        if loose:
            if not plu:
                row.warnings.append("Loose item without a scale code: it can only be billed by name.")
        elif not options.generate_barcodes:
            row.warnings.append("No barcode: it can only be billed by name or SKU.")


# ── Saving ────────────────────────────────────────────────────────────────────

def apply(rows: list[_Row], options: ImportOptions, actor: User, filename: str) -> ImportResult:
    """Saves an analysed file that has no errors, all in one transaction."""
    if any(r.errors for r in rows):
        raise BadRequestError("Fix the rows with errors first.")
    if not has_permission(actor.role, "products.cost"):  # purchase cost: admin / manager only
        for row in rows:
            row.values.pop("cost_price", None)
    look = _Lookups.load()
    inv = InventoryRepository()
    created = updated = stock_rows = 0
    generated: list[GeneratedBarcode] = []
    new_categories: list[str] = []

    with transaction():
        for row in rows:
            v = row.values
            category_id = _category_id(v.get("category"), look, new_categories)
            supplier_id = look.suppliers[v["supplier_code"]].id if "supplier_code" in v else None

            if row.match is None:
                loose = v.get("is_variable_weight", False)
                product = Product(
                    sku=v.get("sku") or "TEMP",
                    name=v["name"],
                    price=v["price"],
                    tax_rate=v.get("tax_rate", Decimal("0")),
                    mrp=v.get("mrp"),
                    hsn_code=v.get("hsn_code"),
                    uom=v.get("uom", UOMType.KG if loose else UOMType.PCS),
                    is_variable_weight=loose,
                    plu_code=v.get("plu_code"),
                    category_id=category_id,
                    supplier_id=supplier_id,
                    store_id=options.store_id if options.sold_in == "store" else None,
                    cost_price=v.get("cost_price"),
                )
                db.session.add(product)
                db.session.flush()
                if "sku" not in v:
                    product.sku = f"SKU-{product.id:05d}"
                link_supplier(product)
                for code in row.barcodes:  # at most one (checked in analyse)
                    _add_barcode_to_product(product, code, _infer_barcode_type(code))
                if not row.barcodes and not loose and options.generate_barcodes:
                    pb = _add_barcode_to_product(product, next_inhouse_barcode(), BarcodeType.IN_HOUSE)
                    generated.append(GeneratedBarcode(product_id=product.id, name=product.name, barcode=pb.barcode))
                qty = v.get("opening_stock")
                if qty:
                    stock = inv.lock_or_create(options.store_id, product.id)
                    stock.qty_on_hand = Decimal(stock.qty_on_hand) + qty
                    batch_service.add(options.store_id, product.id, qty, source="opening",
                                      expiry_date=v.get("expiry_date"), unit_cost=v.get("cost_price"))
                    inv.add_transaction(
                        options.store_id, product.id, InventoryTxnType.ADJUSTMENT, qty,
                        notes=OPENING_STOCK_NOTE, expiry_date=v.get("expiry_date"),
                    )
                    stock_rows += 1
                created += 1
            else:
                product = row.match
                for col in ("name", "price", "tax_rate", "mrp", "hsn_code", "uom", "is_variable_weight", "plu_code",
                            "cost_price"):
                    if col in v:
                        setattr(product, col, v[col])
                if not product.is_variable_weight:
                    product.plu_code = None
                if "category" in v:
                    product.category_id = category_id
                if supplier_id is not None:
                    product.supplier_id = supplier_id
                    link_supplier(product)
                if row.barcodes and not product.barcodes:  # a different saved barcode is a row error in analyse
                    _add_barcode_to_product(product, row.barcodes[0], _infer_barcode_type(row.barcodes[0]))
                updated += 1

        audit_service.log(
            actor, "product.import", "product", None, None,
            {"file": filename, "created": created, "updated": updated, "opening_stock_rows": stock_rows,
             "store_id": options.store_id},
        )
    return ImportResult(
        created=created, updated=updated, opening_stock_rows=stock_rows,
        new_categories=new_categories, generated_barcodes=generated,
    )


def _category_id(name: str | None, look: _Lookups, created: list[str]) -> int | None:
    if not name:
        return None
    key = name.strip().lower()
    if key not in look.categories:
        category = Category(name=name.strip())
        db.session.add(category)
        db.session.flush()
        look.categories[key] = category
        created.append(category.name)
    return look.categories[key].id


# ── Template ──────────────────────────────────────────────────────────────────

TEXT_COLUMNS = {"sku", "barcodes", "plu_code", "hsn_code", "supplier_code"}
EXAMPLES = [
    ["Parle-G 100g", 9.5, 5, 10, "1905", "pcs", "Biscuits", "", "8901719101038", "no", "", "", 50, "", 8.2],
    ["Tata Salt 1kg", 26, 5, 28, "2501", "pcs", "Grocery", "", "", "no", "", "", 20, "", 22],
    ["साखर (सुटी)", 42, 0, "", "1701", "kg", "Loose", "", "", "yes", "123", "", 100, "", 38],
]
INSTRUCTIONS = [
    ("How to fill this sheet", "ही sheet कशी भरायची"),
    ("Required for a new product: name and price (before GST).", "नवीन product साठी लागतंच: name आणि price (GST आधीची किंमत)."),
    ("If the SKU or a barcode already exists, that product is updated: price, MRP, GST, HSN… Blank cells keep the saved value.",
     "SKU किंवा barcode आधीच system मध्ये असेल तर तोच product update होतो (price, MRP, GST, HSN…). रिकामा cell = जुनीच value."),
    ("barcodes: one barcode per product (e.g. 8901234567890). Keep this column as Text so Excel doesn't change the number.",
     "barcodes: एका product ला एकच barcode. हा column Text format मध्येच ठेवा, नाहीतर Excel नंबर बदलतो (8.9E+12)."),
    ("No barcode? Tick 'auto-generate' on the import screen and print stickers from Label Print afterwards.",
     "Barcode नाही? Import screen वर 'auto-generate' ठेवा आणि नंतर Label Print मधून stickers काढा."),
    ("uom: pcs, kg, g, ltr, ml or pack.", "uom: pcs, kg, g, ltr, ml किंवा pack."),
    ("cost_price: what you pay the supplier per unit (or per kg), before GST. Used for the profit report; admin only.",
     "cost_price: supplier ला दिलेली एका नगाची (किंवा किलोची) किंमत, GST आधीची. Profit report साठी; फक्त admin."),
    ("is_variable_weight: yes for loose items sold by weight (sugar, dal). plu_code = the item code set on the weighing scale.",
     "is_variable_weight: सुट्या (वजनावर) वस्तूंसाठी yes. plu_code = वजन काट्यावर सेट केलेला item code."),
    ("category: the category name. A new name creates the category.", "category: category चं नाव. नवीन नाव असेल तर category तयार होते."),
    ("supplier_code: from the Suppliers page (e.g. SUP-1A2B3C). The supplier must exist.",
     "supplier_code: Suppliers page वरचा code. Supplier आधी तयार असला पाहिजे."),
    ("opening_stock: only for NEW products; goes into the store chosen on the import screen. expiry_date: DD-MM-YYYY.",
     "opening_stock: फक्त नवीन products साठी; import screen वर निवडलेल्या दुकानात जमा होतो. expiry_date: DD-MM-YYYY."),
    ("Delete the 3 example rows before importing.", "Import करण्याआधी 3 उदाहरणाच्या rows काढून टाका."),
]


def template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Products"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="E0E7FF")
    for example in EXAMPLES:
        ws.append(example)
    for i, col in enumerate(COLUMNS, start=1):
        letter = ws.cell(row=1, column=i).column_letter
        ws.column_dimensions[letter].width = 26 if col in ("name", "barcodes") else 15
        if col in TEXT_COLUMNS:  # keep long numbers and leading zeros exactly as typed
            for r in range(2, MAX_ROWS + 2):
                ws.cell(row=r, column=i).number_format = "@"
    ws.freeze_panes = "A2"
    uom_col = ws.cell(row=1, column=COLUMNS.index("uom") + 1).column_letter
    loose_col = ws.cell(row=1, column=COLUMNS.index("is_variable_weight") + 1).column_letter
    for col, choices in ((uom_col, "pcs,kg,g,ltr,ml,pack"), (loose_col, "yes,no")):
        dv = DataValidation(type="list", formula1=f'"{choices}"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}{MAX_ROWS + 1}")

    help_ws = wb.create_sheet("Instructions")
    for en, mr in INSTRUCTIONS:
        help_ws.append([en, mr])
    help_ws["A1"].font = help_ws["B1"].font = Font(bold=True)
    help_ws.column_dimensions["A"].width = 90
    help_ws.column_dimensions["B"].width = 90

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
