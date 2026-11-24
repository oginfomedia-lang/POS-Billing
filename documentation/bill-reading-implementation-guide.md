# Reading supplier bills with Tesseract: implementation guide

> **Update (Nov 2026): RapidOCR is now the main engine.** Tesseract misread phone photos and scans badly. One bill
> photo's supplier GSTIN came out as `72OIBZZ2522Z5Z9` and blocked the bill as "supplier not saved". What changed
> since this guide was written:
> - `app/ocr/engine.py` now picks the engine:
>   - `rapid_engine.py` (RapidOCR, PaddleOCR's PP-OCRv6 models on ONNX Runtime): offline, and its models ship
>     inside the `rapidocr` pip package.
>   - `tesseract_engine.py`: the code below, now only the fallback.
>   - Set `OCR_ENGINE=tesseract` to go back to Tesseract.
> - RapidOCR reads the grey picture: `preprocess.prepare(..., binarize=False)` evens out the contrast (CLAHE) but does
>   not make the image black and white.
> - A PDF whose page is one big picture with some program's OCR text laid over it ("OCR ready") is read again by our
>   engine. Its own text is used only to help find the GSTIN and invoice number (`Page.scan`).
> - GSTIN (`header_parser.closest_gstin`):
>   - A GSTIN with up to 2 characters misread, or one cut off at the edge of the photo (10+ characters left), matches
>     the one saved supplier it is that close to.
>   - State codes other than 01–38, 97 and 99 are noise.
>   - Only a GSTIN read for sure (its check digit is right) that no supplier has gives the red "supplier not saved".
>     Anything less certain gives "check the supplier".
> - `OCR_TIMEOUT_SECONDS` is now 150. RapidOCR takes about 10–20 s a page on an office PC, and the screen now waits
>   200 s.
> - Installer: `literetailer-backend.spec` collects `rapidocr`, `onnxruntime`, `omegaconf`, `pyclipper` and
>   `shapely`. The installer grows by about 60–80 MB.

This guide adds **"Read from bill"** to the Direct purchase screen (Purchases → *Goods arrived without PO*). The user
picks the supplier's bill (PDF or photo) and clicks the button. The Main PC reads it, then fills in the supplier,
invoice number, date, bill total and item lines. The user checks the lines and saves as usual. When the bill is saved,
the app remembers what this supplier calls each product, so their next bill matches by itself.

## How to use this guide

- Work through the parts in order: **A** (set up your PC), **B** (backend), **C** (frontend), **D** (installer).
- **New files** are given in full. You have already created most of them as empty files; type the content in.
- **Changes to existing files** give the exact line number and the current text of that line, then the code to add
  or to replace it with. Line numbers are those of the file **before** you change it. Within each file the changes
  are listed **from the bottom up**, so doing them in the order shown keeps every number correct.
- Code blocks don't show empty lines at their end. In Python files, keep **two empty lines** between top-level
  functions and classes, as in the rest of each file.
- Every code block here was copied by a script from a working copy of the project with the feature added. That copy
  passed the whole backend test suite (608 tests, including the new ones), `npm run typecheck` and `npm test`.
  The OCR path was tested with real Tesseract 5.5 on a scanned page and on tilted, blurred and grainy fake phone
  photos (`test_photo_read_by_tesseract`). Not tested yet: real supplier bills, and the PyInstaller/installer build.

## How it works (the flow)

```
User picks the bill (PDF/photo) on Direct purchase → clicks "Read from bill"
        │  POST /api/v1/purchases/direct/extract   (file, store_id, supplier_id optional)
        ▼
bill_ocr_service.extract_bill()
   1. Is it a PDF made by billing software?  ── yes ─► pdf_text: take its words (exact, no OCR)
        │ no (scanned PDF or photo)
        ▼
   2. rasterize: PDF page → 300 DPI image, or open the photo (EXIF rotation applied)
   3. preprocess: flatten a tilted photo, enlarge/reduce, straighten, remove noise, black & white
   4. engine: Tesseract → words with their boxes and confidence
        ▼
   5. header_parser: GSTINs (checksum verified), invoice no., date, taxable/CGST/SGST/IGST/round-off/grand total
   6. table_parser: words → rows → find the header row (Qty, Rate, Amount …) → columns → item lines
         (no header readable? use this supplier's saved layout from supplier_bill_templates)
   7. normalize: "1,24,500.00" → 124500.00, "1O" → 10, "10+1" → 10 + 1 free, "OCT-27" → 31 Oct 2027
   8. checks: qty × rate (− discount) (+ GST) = amount?  lines add up to the bill total?
   9. bill_matching_service: alias → supplier item code → barcode → fuzzy name (rapidfuzz + search_key)
        ▼
JSON draft → the screen fills the form:
   green line   = matched          yellow line = matched but please check (shows why)
   red panel    = no product found: click a suggestion, pick it in the search, or create the product
        ▼
User saves as before: POST /purchases/direct (each line also sends bill_description)
        ▼
direct_purchase_service saves PO + receipt + invoice and calls bill_matching_service.remember()
   → supplier_item_aliases: (supplier, bill text) → product, used first on the next bill
```

Nothing is saved while reading, except the supplier's column layout.

---

# Part A: Set up your PC

### A1. Install Tesseract

1. Download the Windows installer from the UB Mannheim build page:
   <https://github.com/UB-Mannheim/tesseract/wiki> (file `tesseract-ocr-w64-setup-5.x.x.exe`).
2. Run it. On the **Choose Components** page, open **Additional language data** and tick **Marathi**. English
   is included already. Keep the folder `C:\Program Files\Tesseract-OCR`.
3. Check it in PowerShell:

```powershell
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --version
& "C:\Program Files\Tesseract-OCR\tesseract.exe" --list-langs     # should list eng and mar
```

4. Tell the backend where it is. Add this line to `backend\.env` (development PC):

```text
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

The installed app doesn't need this line: it uses the copy bundled in the installer (Part D).

### A2. Python packages

Do step B1 (requirements.txt) first, then install:

```powershell
cd backend
.venv\Scripts\pip install -r requirements.txt
```

---

# Part B: Backend

### B1. `backend/requirements.txt`: the new packages

| Package | What for |
|---|---|
| pytesseract | runs tesseract.exe from Python |
| pdfplumber | text and word positions of digital PDFs |
| pypdfium2 | scanned PDF pages → images (no Poppler install needed) |
| opencv-python-headless + numpy | cleaning photos |
| Pillow | opening images (already installed through fpdf2; now listed directly) |
| rapidfuzz | fast fuzzy matching of bill names to product names |

File: `backend/requirements.txt`. **1 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 25**, which is:

```text
cryptography>=42,<47
```

add these lines:

```text
# Reading supplier bills on Direct purchase (app/ocr). Tesseract itself is a separate program (tesseract.exe),
# bundled with the installer. pdfplumber = text of digital PDFs, pypdfium2 = scanned PDF pages to images,
# OpenCV = cleaning photos, rapidfuzz = matching bill names to products.
pytesseract>=0.3.13,<0.4
pdfplumber>=0.11,<0.12
pypdfium2>=4.30,<6
opencv-python-headless>=4.10,<6
numpy>=1.26,<3
Pillow>=10,<14
rapidfuzz>=3.9,<4
```

### B2. `backend/app/config/base.py`: settings

All of them can be changed in `.env` / `backend.env` without touching code.

File: `backend/app/config/base.py`. **1 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 102** (the empty line below line 101). Line 101 is:

```python
    UPLOAD_MAX_BYTES = int(os.environ.get("UPLOAD_MAX_BYTES") or str(20 * 1024 * 1024))  # 20 MB
```

add these lines:

```python
    # --- Reading supplier bills (app/ocr, Direct purchase → "Read from bill") ---
    # Full path to tesseract.exe. Empty = the copy bundled with the installer, else "tesseract" on PATH.
    TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "")
    # Tesseract languages: "eng", or "eng+mar" for bills with Marathi item names (slower).
    OCR_LANGUAGES = os.environ.get("OCR_LANGUAGES") or "eng"
    # Page layout mode: 6 = one block of text (most bills); try 4 or 11 if a supplier's bill reads badly.
    OCR_PSM = int(os.environ.get("OCR_PSM") or "6")
    OCR_MAX_PAGES = int(os.environ.get("OCR_MAX_PAGES") or "5")
    OCR_TIMEOUT_SECONDS = int(os.environ.get("OCR_TIMEOUT_SECONDS") or "90")  # for the whole bill
```

### B3. Models: two new tables

`supplier_item_aliases` remembers *"this supplier writes **TATA SALT 1KG** for our product 41"*.
`supplier_bill_templates` keeps where each column was on the supplier's last bill.

**Whole file** (33 lines): `backend/app/models/supplier_item_alias.py`

```python
"""What a supplier calls a product on their bill → our product.

Learnt when a Direct purchase read from the bill (OCR) is saved, so their next bill matches by itself, even
when the bill says "TATA SALT 1KG" and the product is "टाटा मीठ 1 किलो".
"""
from app.extensions import db
from app.models.base import TimestampMixin


class SupplierItemAlias(TimestampMixin, db.Model):
    __tablename__ = "supplier_item_aliases"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(
        db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # search_key() of the bill's text (app/utils/search_key.py): spaces, case and vowel misreads don't matter.
    description_key = db.Column(db.String(400), nullable=False)
    description = db.Column(db.String(300), nullable=False)  # as last printed on the bill, for people
    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    times_used = db.Column(db.Integer, nullable=False, default=1)

    __table_args__ = (
        db.UniqueConstraint("supplier_id", "description_key", name="uq_supplier_item_aliases_supplier_key"),
    )

    supplier = db.relationship("Supplier")
    product = db.relationship("Product")

    def __repr__(self) -> str:
        return f"<SupplierItemAlias {self.description!r} → product {self.product_id}>"
```

**Whole file** (23 lines): `backend/app/models/supplier_bill_template.py`

```python
"""A supplier's bill layout: where each column is, saved the last time their bill's table header was read.

Used when a later bill's header can't be read (blurred photo, cut off): the columns are taken from here.
"""
from app.extensions import db
from app.models.base import TimestampMixin


class SupplierBillTemplate(TimestampMixin, db.Model):
    __tablename__ = "supplier_bill_templates"

    id = db.Column(db.Integer, primary_key=True)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False)
    # [{"field": "qty", "x0": 0.41, "x1": 0.47}, ...]: each column's left/right edge as a share of the page width
    columns = db.Column(db.JSON, nullable=False)
    times_used = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint("supplier_id", name="uq_supplier_bill_templates_supplier"),)

    supplier = db.relationship("Supplier")

    def __repr__(self) -> str:
        return f"<SupplierBillTemplate supplier={self.supplier_id}>"
```

Register both in `backend/app/models/__init__.py` so Alembic and the tests see them:

File: `backend/app/models/__init__.py`. **1 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 27**, which is:

```python
from app.models.supplier_return import SupplierReturn  # noqa: F401
```

add these lines:

```python
from app.models.supplier_item_alias import SupplierItemAlias  # noqa: F401
from app.models.supplier_bill_template import SupplierBillTemplate  # noqa: F401
```

### B4. Migration

Create the file below. It must come after the current head `c4e8a2f6b9d1` (`sale_customer_name`). If you
add other migrations first, run `flask db heads` and put that revision in `down_revision`.

**Whole file** (49 lines): `backend/migrations/versions/d6b3f8a1c5e2_bill_ocr_tables.py`

```python
"""Reading supplier bills: supplier_item_aliases (bill text → product) and supplier_bill_templates (column layout)

Revision ID: d6b3f8a1c5e2
Revises: c4e8a2f6b9d1
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa


revision = "d6b3f8a1c5e2"
down_revision = "c4e8a2f6b9d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "supplier_item_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description_key", sa.String(400), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("supplier_id", "description_key", name="uq_supplier_item_aliases_supplier_key"),
    )
    op.create_index("ix_supplier_item_aliases_supplier_id", "supplier_item_aliases", ["supplier_id"])
    op.create_index("ix_supplier_item_aliases_product_id", "supplier_item_aliases", ["product_id"])

    op.create_table(
        "supplier_bill_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("columns", sa.JSON(), nullable=False),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("supplier_id", name="uq_supplier_bill_templates_supplier"),
    )


def downgrade():
    op.drop_table("supplier_bill_templates")
    op.drop_index("ix_supplier_item_aliases_product_id", table_name="supplier_item_aliases")
    op.drop_index("ix_supplier_item_aliases_supplier_id", table_name="supplier_item_aliases")
    op.drop_table("supplier_item_aliases")
```

Apply it:

```powershell
cd backend
.venv\Scripts\flask --app wsgi db upgrade
.venv\Scripts\flask --app wsgi db heads      # should print: d6b3f8a1c5e2 (head)
```

### B5. The `app/ocr` package (8 files)

You already have these files, empty. They depend on each other only in this direction:
`__init__` (Word, Page) ← `normalize` ← `header_parser`, `table_parser`; `pdf_text`, `rasterize`, `preprocess`,
`engine` stand alone.

#### B5.1 `app/ocr/__init__.py`: the two data types used everywhere

`Word` is one word plus its box on the page. `Page` holds a page's words.

**Whole file** (46 lines): `backend/app/ocr/__init__.py`

```python
"""Reading supplier bills (PDF or photo) for the Direct purchase screen.

    pdf_text      PDF made by billing software → its words (no OCR needed, exact)
    rasterize     scanned PDF pages / photos → images
    preprocess    straightens and cleans an image (OpenCV)
    engine        Tesseract: image → words with their boxes
    header_parser GSTIN, invoice number, date, totals
    table_parser  words → item lines (rows, columns, supplier layouts)
    normalize     OCR text → numbers and dates

The whole pipeline is app/services/bill_ocr_service.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Word:
    """One word and its box on the page: pixels for images, PDF points for digital PDFs."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    conf: float = 100.0  # Tesseract's confidence 0-100; 100 for text taken from a digital PDF

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Page:
    width: float
    height: float
    words: list[Word] = field(default_factory=list)
    source: str = "ocr"  # "pdf_text" (digital PDF) or "ocr" (Tesseract)
```

#### B5.2 `app/ocr/normalize.py`: OCR text → numbers and dates

The letter → digit fixes (`O`→`0`, `l`→`1`, `S`→`5` …) are applied only when the text is mostly digits, so
item names are never changed. Units (`PCS`, `KG`, `%`) and currency (`₹`, `Rs.`) are removed first.
`taxable_value()` is the arithmetic check used both by the table parser and by the service.

**Whole file** (124 lines): `backend/app/ocr/normalize.py`

```python
"""OCR text → numbers and dates. Fixes the usual misreads (O→0, l→1, S→5) only in text that is mostly digits."""
from __future__ import annotations

import calendar
import re
from datetime import date
from decimal import Decimal, InvalidOperation

# Letters Tesseract often returns instead of digits.
_DIGIT_FIXES = str.maketrans({"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "i": "1", "|": "1",
                              "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2"})
# Removed before the digit fixes, else "PCS" would turn into "PC5".
_CURRENCY = re.compile(r"(?i)^\s*(₹|rs\.?|inr)\s*")
_UNIT_SUFFIX = re.compile(r"(?i)\s*(pcs?|nos?|kgs?|gms?|gm|ltrs?|boxe?s?|cs|cases?|doz|%)\.?\s*$")
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}


def to_decimal(text: str | None) -> Decimal | None:
    """ "1,24,500.00" → 124500.00, "24.50/-" → 24.50, "1O" → 10, "₹ 99" → 99, "10 PCS" → 10; words → None."""
    if text is None:
        return None
    s = _CURRENCY.sub("", str(text).strip())
    s = _UNIT_SUFFIX.sub("", s).replace(" ", "")
    digits = sum(c.isdigit() for c in s)
    if digits == 0 or digits < len(s) / 2:
        return None  # a word, not a number
    s = s.translate(_DIGIT_FIXES)
    s = re.sub(r"[^\d.,\-]", "", s)
    negative = s.startswith("-")
    s = s.replace("-", "")
    if re.fullmatch(r"\d+,\d{1,2}", s):
        s = s.replace(",", ".")  # 24,50 = decimal comma
    else:
        s = s.replace(",", "")  # 1,24,500 = thousands
    if s.count(".") > 1:
        head, _, tail = s.rpartition(".")
        s = head.replace(".", "") + "." + tail
    s = s.strip(".")
    if not s:
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def parse_qty(text: str | None) -> tuple[Decimal | None, Decimal | None]:
    """ "10" → (10, None); "10+1" → (10, 1): 1 free."""
    if not text:
        return None, None
    m = re.fullmatch(r"\s*([^+]+?)\s*\+\s*([^+]+?)\s*", text)
    if m:
        return to_decimal(m[1]), to_decimal(m[2])
    return to_decimal(text), None


def _year(text: str) -> int:
    n = int(text)
    return n + 2000 if n < 100 else n


def parse_date(text: str | None) -> date | None:
    """Indian order: 15/11/2026, 15-11-26, 15.11.2026, 15-Nov-2026, 15 November 26."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})", text)
    if m:
        day, month, year = int(m[1]), int(m[2]), _year(m[3])
    else:
        m = re.search(r"(\d{1,2})[\s\-./]*([A-Za-z]{3})[A-Za-z]*[\s\-./,]*(\d{2,4})", text)
        if not m or m[2].lower() not in _MONTHS:
            return None
        day, month, year = int(m[1]), _MONTHS[m[2].lower()], _year(m[3])
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_expiry(text: str | None) -> date | None:
    """A full date, or month/year (10/27, OCT-27, Oct 2027) → the last day of that month."""
    if not text:
        return None
    full = parse_date(text)
    if full:
        return full
    m = re.search(r"(\d{1,2})\s*[/\-.]\s*(\d{2,4})", text)
    if m:
        month, year = int(m[1]), _year(m[2])
    else:
        m = re.search(r"([A-Za-z]{3})[A-Za-z]*[\s\-./,]*(\d{2,4})", text)
        if not m or m[1].lower() not in _MONTHS:
            return None
        month, year = _MONTHS[m[1].lower()], _year(m[2])
    if not 1 <= month <= 12:
        return None
    return date(year, month, calendar.monthrange(year, month)[1])


def clean_hsn(text: str | None) -> str | None:
    """HSN codes are 4-8 digits; anything else → None."""
    if not text:
        return None
    s = re.sub(r"\D", "", text.translate(_DIGIT_FIXES))
    return s if 4 <= len(s) <= 8 else None


def taxable_value(qty: Decimal, rate: Decimal, amount: Decimal,
                  discount: Decimal | None, gst: Decimal | None) -> Decimal | None:
    """qty × rate (after the discount, % or ₹) when that, or that + GST, gives the amount printed on the line.
    None when nothing fits: the line was misread."""
    gross = qty * rate
    options = [gross]
    if discount:
        options += [gross * (1 - discount / 100), gross - discount]
    tolerance = max(Decimal("1"), abs(amount) * Decimal("0.005"))
    for value in options:
        if abs(value - amount) <= tolerance:
            return value
        if gst and abs(value * (1 + gst / 100) - amount) <= tolerance:
            return value
    return None
```

#### B5.3 `app/ocr/header_parser.py`: GSTIN, invoice number, date, totals

- **GSTIN**: every 15-character window is cleaned place by place (a digit place can't hold `O`, a letter place
  can't hold `0`), then its **check digit** is verified, so random text is never taken for a GSTIN. The bill shows
  the supplier's GSTIN and the store's; the service picks the one that belongs to a supplier.
- **Totals**: searched from the bottom of the bill upwards, taking the right-most amount on the line.

**Whole file** (115 lines): `backend/app/ocr/header_parser.py`

```python
"""The bill's header and footer: GSTINs, invoice number, invoice date and the printed totals."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.ocr.normalize import parse_date, to_decimal

_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN_SHAPE = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
# What each of the 15 places must be: D digit, L letter, X either, Z the letter Z.
_GSTIN_PLACES = "DDLLLLLDDDDLXZX"
_TO_DIGIT = str.maketrans("OIlSBZQD", "01158200")
_TO_LETTER = str.maketrans("01258", "OIZSB")

_INVOICE_NO = re.compile(
    r"(?i)\b(?:invoice|inv|bill)\.?\s*(?:number|no\b|#)\.?\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-]{0,29})")
_DATE_LABEL = re.compile(r"(?i)\b(?:invoice\s*date|inv\.?\s*date|bill\s*date|dated|date)\b\s*[:\-]?\s*(.{6,24})")
_AMOUNT = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_TOTALS = (
    ("grand_total", re.compile(r"(?i)\b(grand\s*total|net\s*(amount|amt|payable)|bill\s*amount|invoice\s*(total|amount)"
                               r"|total\s*amount|amount\s*payable)\b")),
    ("taxable_total", re.compile(r"(?i)\b(taxable\s*(value|amount|amt)|sub\s*-?\s*total)\b")),
    ("cgst", re.compile(r"(?i)\bcgst\b")),
    ("sgst", re.compile(r"(?i)\b(sgst|utgst)\b")),
    ("igst", re.compile(r"(?i)\bigst\b")),
    ("round_off", re.compile(r"(?i)\bround(ed|ing)?\s*-?\s*off\b|\br/o\b")),
)
_PLAIN_TOTAL = re.compile(r"(?i)^\W*total\b")


@dataclass
class BillHeader:
    gstins: list[str] = field(default_factory=list)  # every valid GSTIN on the bill: supplier's and the store's
    invoice_number: str | None = None
    invoice_date: date | None = None
    taxable_total: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None
    round_off: Decimal | None = None
    grand_total: Decimal | None = None


def gstin_checksum_ok(gstin: str) -> bool:
    """The 15th character of a GSTIN is a check digit over the first 14."""
    total = 0
    for i, ch in enumerate(gstin[:14]):
        product = _GSTIN_CHARS.index(ch) * (2 if i % 2 else 1)
        total += product // 36 + product % 36
    return _GSTIN_CHARS[(36 - total % 36) % 36] == gstin[14]


def _fix_gstin(raw: str) -> str:
    """OCR mix-ups put right by place: a digit place can't hold O, a letter place can't hold 0."""
    out = []
    for ch, kind in zip(raw, _GSTIN_PLACES):
        if kind == "D":
            ch = ch.translate(_TO_DIGIT)
        elif kind == "L":
            ch = ch.translate(_TO_LETTER)
        elif kind == "Z" and ch == "2":
            ch = "Z"
        out.append(ch)
    return "".join(out)


def find_gstins(lines: list[str]) -> list[str]:
    found: list[str] = []
    for line in lines:
        compact = re.sub(r"[^0-9A-Za-z]", "", line).upper()
        for i in range(len(compact) - 14):
            gstin = _fix_gstin(compact[i:i + 15])
            if _GSTIN_SHAPE.fullmatch(gstin) and gstin_checksum_ok(gstin) and gstin not in found:
                found.append(gstin)
    return found


def _last_amount(line: str) -> Decimal | None:
    amounts = _AMOUNT.findall(line)
    return to_decimal(amounts[-1]) if amounts else None


def parse(lines: list[str]) -> BillHeader:
    """lines = the text of every row on every page, top to bottom."""
    header = BillHeader(gstins=find_gstins(lines))

    for line in lines:
        m = _INVOICE_NO.search(line)
        if m:
            header.invoice_number = m[1].strip("-/")
            break

    for line in lines:
        m = _DATE_LABEL.search(line)
        if m and (d := parse_date(m[1])):
            header.invoice_date = d
            break
    if header.invoice_date is None:  # no "Date:" label: the first date near the top
        header.invoice_date = next((d for line in lines[:15] if (d := parse_date(line))), None)

    # Totals are at the bottom: search upwards, take the right-most amount on the line.
    for name, pattern in _TOTALS:
        for line in reversed(lines):
            if pattern.search(line) and (amount := _last_amount(line)) is not None:
                setattr(header, name, amount)
                break
    if header.grand_total is None:  # just "Total ...... 1,234.00"
        for line in reversed(lines):
            if _PLAIN_TOTAL.search(line) and (amount := _last_amount(line)) is not None:
                header.grand_total = amount
                break
    return header
```

#### B5.4 `app/ocr/table_parser.py`: words → item lines (the core)

1. `group_rows`: words whose vertical centres are within 0.6 × the line height form one row. "Words" with no letter
   or digit (specks on photos read as `_`, `,`, `|`) are dropped first.
2. `find_header`: the row containing the most column names (`HEADER_WORDS`) is the table header, if it has at least
   3 of them including Qty or Amount.
3. `_header_cells`: header words close together form one cell ("Batch No", "Item Name"). Unknown cells
   ("Sr No", "Unit") become `_skip` columns, so their values don't leak into a neighbouring column.
4. Column edges are halfway between header cells, except that the **item name** column runs up to the next
   header (names are long and left-aligned).
5. Each row below the header: every word goes to the column it sits under. A row with only a name continues the
   previous item (wrapped names). A row starting with "Total" or "Sub Total" ends the table. A serial number at the
   start of a name ("1 TATA SALT") is removed when it equals the line's position.
6. No header on the page? The supplier's saved layout is used, and then only rows whose arithmetic works are kept.

**Whole file** (217 lines): `backend/app/ocr/table_parser.py`

```python
"""Words with positions → the bill's item lines.

1. Words whose vertical centres line up form a row.
2. The row with the most column names (Qty, Rate, Amount ...) is the table header; each header word marks
   where its column is. A supplier's last good layout (supplier_bill_templates) is used when no header is found.
3. Every row below the header: each word goes to the column it sits under. A row with only a name continues
   the line above (long names wrap); a "Total" row ends the table.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.ocr import Page, Word
from app.ocr.normalize import clean_hsn, parse_expiry, parse_qty, taxable_value, to_decimal

SKIP = "_skip"  # a column we don't use (Sr. No., Unit, CGST Amt ...)

# Header words (lower case, only letters and %) → our field.
HEADER_WORDS = {
    "description": "name", "particulars": "name", "particular": "name", "item": "name", "items": "name",
    "itemname": "name", "product": "name", "productname": "name", "goods": "name", "name": "name",
    "hsn": "hsn", "hsnsac": "hsn", "hsncode": "hsn", "sac": "hsn",
    "qty": "qty", "qnty": "qty", "quantity": "qty", "nos": "qty", "billqty": "qty",
    "free": "free", "sch": "free", "fqty": "free", "freeqty": "free",
    "rate": "rate", "price": "rate", "prate": "rate", "purrate": "rate", "unitprice": "rate",
    "mrp": "mrp",
    "disc": "discount", "disc%": "discount", "discount": "discount", "dis%": "discount", "dis": "discount",
    "cd%": "discount",
    "gst": "gst", "gst%": "gst", "tax%": "gst", "gstrate": "gst", "taxrate": "gst", "igst%": "gst",
    "batch": "batch", "batchno": "batch", "bno": "batch", "lot": "batch",
    "exp": "expiry", "expiry": "expiry", "expdt": "expiry", "expdate": "expiry",
    "amount": "amount", "amt": "amount", "value": "amount", "netamt": "amount", "total": "amount",
    "netvalue": "amount",
}
_END_OF_TABLE = re.compile(r"(?i)^\W*(sub\s*-?\s*total|grand\s*total|total|taxable|amount\s*in\s*words|rupees)\b")


@dataclass
class Row:
    words: list[Word]

    @property
    def yc(self) -> float:
        return sum(w.yc for w in self.words) / len(self.words)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Column:
    field: str
    x0: float
    x1: float


@dataclass
class RawLine:
    description: str
    hsn: str | None
    qty: Decimal | None
    free_qty: Decimal | None
    rate: Decimal | None
    mrp: Decimal | None
    discount: Decimal | None
    gst: Decimal | None
    batch: str | None
    expiry: date | None
    amount: Decimal | None
    confidence: float  # the lowest OCR confidence of the row's words
    page: int


def group_rows(words: list[Word]) -> list[Row]:
    """Words → rows, top to bottom; each row's words left to right. "Words" with no letter or digit are dropped:
    on photos they are specks read as "_", ",", "|", and they would glue "Sr" onto "Description" or end up in names."""
    words = [w for w in words if re.search(r"[A-Za-z0-9]", w.text)]
    if not words:
        return []
    heights = sorted(w.height for w in words)
    line_height = heights[len(heights) // 2] or 1
    rows: list[Row] = []
    for w in sorted(words, key=lambda w: w.yc):
        if rows and abs(w.yc - rows[-1].yc) <= 0.6 * line_height:
            rows[-1].words.append(w)
        else:
            rows.append(Row([w]))
    for row in rows:
        row.words.sort(key=lambda w: w.x0)
    return rows


def _header_field(text: str) -> str | None:
    return HEADER_WORDS.get(re.sub(r"[^a-z%]", "", text.lower()))


def _header_cells(row: Row) -> list[list]:
    """Header words → cells [field, x0, x1]. Words close together are one cell ("Batch No", "Item Name"),
    unless they name two different columns ("Qty Rate" printed tight)."""
    gap_limit = max(w.height for w in row.words)  # about one letter height: a space, not a column gap
    cells: list[list] = []
    for w in row.words:
        f = _header_field(w.text)
        if cells and w.x0 - cells[-1][2] < gap_limit and (cells[-1][0] is None or f is None or cells[-1][0] == f):
            cells[-1][0] = cells[-1][0] or f
            cells[-1][2] = w.x1
        else:
            cells.append([f, w.x0, w.x1])
    # Each field once: the right-most "Amount" (the line total), the first of any other.
    last_amount = max((i for i, c in enumerate(cells) if c[0] == "amount"), default=None)
    seen: set[str] = set()
    for i, cell in enumerate(cells):
        f = cell[0]
        if f is None or (f == "amount" and i != last_amount) or (f != "amount" and f in seen):
            cell[0] = SKIP
        else:
            seen.add(f)
    return cells


def find_header(rows: list[Row], page_width: float) -> tuple[int, list[Column]] | None:
    """(index of the header row, its columns), or None when no row looks like a table header."""
    best: tuple[int, int] | None = None  # (fields found, row index)
    for i, row in enumerate(rows):
        fields = {f for w in row.words if (f := _header_field(w.text))}
        if len(fields) >= 3 and ({"qty", "amount"} & fields) and (best is None or len(fields) > best[0]):
            best = (len(fields), i)
    if best is None:
        return None
    header = rows[best[1]]
    cells = _header_cells(header)
    letter = max(w.height for w in header.words)
    # Where one column ends and the next begins: halfway between their header words, except after the item
    # name: names are long and written from the left, so that column runs up to the next header word.
    bounds = []
    for left_cell, right_cell in zip(cells, cells[1:]):
        if left_cell[0] == "name":
            bounds.append(right_cell[1] - 0.5 * letter)
        else:
            bounds.append((left_cell[2] + right_cell[1]) / 2)
    edges = [0.0] + bounds + [page_width]
    columns = [Column(cell[0], edges[i], edges[i + 1]) for i, cell in enumerate(cells)]
    return best[1], columns


def _row_cells(row: Row, columns: list[Column]) -> dict[str, list[Word]]:
    out: dict[str, list[Word]] = defaultdict(list)
    for w in row.words:
        col = next((c for c in columns if c.x0 <= w.xc < c.x1), None)
        if col and col.field != SKIP:
            out[col.field].append(w)
    return out


def parse_page(page: Page, page_no: int, template: list[dict] | None = None) -> tuple[list[RawLine], list[dict] | None]:
    """The page's item lines, and the column layout found on it (fractions of the page width, to save as the
    supplier's template). Layout None = no header on this page (the template was used, or nothing was found)."""
    rows = group_rows(page.words)
    found = find_header(rows, page.width)
    if found:
        start, columns = found
        body = rows[start + 1:]
        layout = [{"field": c.field, "x0": round(c.x0 / page.width, 4), "x1": round(c.x1 / page.width, 4)}
                  for c in columns]
    elif template:
        columns = [Column(c["field"], c["x0"] * page.width, c["x1"] * page.width) for c in template]
        body, layout = rows, None
    else:
        return [], None

    lines: list[RawLine] = []
    for row in body:
        cells = _row_cells(row, columns)
        text = {f: " ".join(w.text for w in ws).strip() for f, ws in cells.items()}
        name = text.get("name", "")
        qty, free = parse_qty(text.get("qty"))
        rate, amount = to_decimal(text.get("rate")), to_decimal(text.get("amount"))
        numbers = sum(v is not None for v in (qty, rate, amount))

        if _END_OF_TABLE.match(name) or (not name and _END_OF_TABLE.search(row.text)):
            if lines:
                break
            continue
        if numbers == 0:
            if name and lines and set(text) == {"name"}:
                lines[-1].description += " " + name  # the name went on to a second line
            continue
        if numbers < 2 or not name:
            continue
        discount, gst = to_decimal(text.get("discount")), to_decimal(text.get("gst"))
        if not found and not (qty and rate is not None and amount is not None
                              and taxable_value(qty, rate, amount, discount, gst) is not None):
            continue  # template only: keep rows whose sums work, so addresses and notes aren't taken as items
        serial = re.match(r"(\d{1,3})[.)]?\s+(.+)", name)
        if serial and int(serial[1]) == len(lines) + 1:
            name = serial[2]  # "1 TATA SALT": the Sr. No. landed in the name column
        lines.append(RawLine(
            description=name,
            hsn=clean_hsn(text.get("hsn")),
            qty=qty,
            free_qty=free if free is not None else to_decimal(text.get("free")),
            rate=rate,
            mrp=to_decimal(text.get("mrp")),
            discount=discount,
            gst=gst,
            batch=text.get("batch") or None,
            expiry=parse_expiry(text.get("expiry")),
            amount=amount,
            confidence=min(w.conf for w in row.words),
            page=page_no,
        ))
    return lines, layout
```

#### B5.5 `app/ocr/pdf_text.py`: digital PDFs (no OCR)

Most distributors' software (Tally, Marg, Busy) makes PDFs that contain real text. Reading it is exact and
instant. A PDF with fewer than 50 characters of text is a scan and goes to OCR instead.

**Whole file** (29 lines): `backend/app/ocr/pdf_text.py`

```python
"""PDFs made by billing software (Tally, Marg, Busy ...) already hold their text: read it, no OCR needed."""
from __future__ import annotations

import io

import pdfplumber

from app.ocr import Page, Word

MIN_TEXT_CHARS = 50  # less than this on all pages = a scanned PDF (only pictures inside)


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def read_text_pages(data: bytes, max_pages: int) -> list[Page] | None:
    """The words of each page with their boxes (PDF points), or None for a scanned PDF."""
    pages: list[Page] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for p in pdf.pages[:max_pages]:
            words = [
                Word(w["text"], float(w["x0"]), float(w["top"]), float(w["x1"]), float(w["bottom"]), 100.0)
                for w in p.extract_words()
            ]
            pages.append(Page(width=float(p.width), height=float(p.height), words=words, source="pdf_text"))
    if sum(len(w.text) for page in pages for w in page.words) < MIN_TEXT_CHARS:
        return None
    return pages
```

#### B5.6 `app/ocr/rasterize.py`: scanned PDF pages and photos → images

**Whole file** (29 lines): `backend/app/ocr/rasterize.py`

```python
"""Scanned PDF pages and photos → images for Tesseract."""
from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image, ImageOps

DPI = 300  # Tesseract reads best at about 300 dots per inch


def pdf_to_images(data: bytes, max_pages: int) -> list[Image.Image]:
    pdf = pdfium.PdfDocument(data)
    try:
        images = []
        for i in range(min(len(pdf), max_pages)):
            page = pdf[i]
            images.append(page.render(scale=DPI / 72).to_pil().convert("RGB"))
            page.close()
        return images
    finally:
        pdf.close()


def load_image(data: bytes) -> Image.Image:
    """A photo or scan. Phones store "rotate me" in the EXIF data instead of turning the picture: apply it."""
    image = Image.open(io.BytesIO(data))
    image = ImageOps.exif_transpose(image)
    return image.convert("RGB")
```

#### B5.7 `app/ocr/preprocess.py`: cleaning the image (OpenCV)

| Step | Why |
|---|---|
| `_flatten_paper` (photos only) | a photo taken at an angle: find the paper's 4 corners and stretch it flat |
| `_limit_size` | Tesseract wants letters about 20+ px high; huge photos are only slower |
| `_deskew` | tries −5°…+5° and keeps the angle where the text rows line up best |
| `medianBlur` | removes camera grain and specks (without it a grainy photo gave no lines at all; `fastNlMeansDenoising` worked too but took ~8 s per page) |
| `adaptiveThreshold` | black text on white, even with shadows |

**Whole file** (82 lines): `backend/app/ocr/preprocess.py`

```python
"""Makes a bill image easy for Tesseract: flat, straight, right size, black text on white."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

MIN_SIDE = 1800  # smaller pictures are enlarged: Tesseract needs letters about 20+ pixels high
MAX_SIDE = 4000  # bigger ones are reduced: slower, no more accurate


def prepare(image: Image.Image, is_photo: bool) -> np.ndarray:
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    if is_photo:
        gray = _flatten_paper(gray)  # only photos: on a scan the "paper" found could be the table's border
    gray = _limit_size(gray)
    gray = _deskew(gray)
    gray = cv2.medianBlur(gray, 3)  # removes specks and grain; fastNlMeansDenoising took ~8 s per page
    # Black and white with a threshold worked out per neighbourhood, so shadows don't turn black.
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)


def _limit_size(gray: np.ndarray) -> np.ndarray:
    longest = max(gray.shape)
    if longest < MIN_SIDE:
        scale = min(2.0, MIN_SIDE / longest)
    elif longest > MAX_SIDE:
        scale = MAX_SIDE / longest
    else:
        return gray
    interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=interpolation)


def _order_corners(pts: np.ndarray) -> np.ndarray:
    """top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()  # y - x
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def _flatten_paper(gray: np.ndarray) -> np.ndarray:
    """A photo taken at an angle: find the paper's four corners and stretch it back into a rectangle."""
    scale = min(1.0, 1000 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
    edges = cv2.Canny(cv2.GaussianBlur(small, (5, 5), 0), 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return gray
    paper = max(contours, key=cv2.contourArea)
    if cv2.contourArea(paper) < 0.6 * small.shape[0] * small.shape[1]:
        return gray  # no clear sheet of paper: leave the picture as it is
    corners = cv2.approxPolyDP(paper, 0.02 * cv2.arcLength(paper, True), True)
    if len(corners) != 4:
        return gray
    tl, tr, br, bl = rect = _order_corners(corners.reshape(4, 2).astype("float32") / scale)
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    target = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(rect, target)
    return cv2.warpPerspective(gray, matrix, (width, height))


def _deskew(gray: np.ndarray) -> np.ndarray:
    """Straightens a page tilted up to 5°: the angle at which the text rows line up best (sharpest row profile)."""
    scale = 800 / gray.shape[1]
    small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    _, ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    h, w = ink.shape
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-5.0, 5.25, 0.25):
        m = cv2.getRotationMatrix2D((w / 2, h / 2), float(angle), 1.0)
        rotated = cv2.warpAffine(ink, m, (w, h), flags=cv2.INTER_NEAREST)
        score = float(np.var(rotated.sum(axis=1)))
        if score > best_score:
            best_angle, best_score = float(angle), score
    if abs(best_angle) < 0.25:
        return gray
    h, w = gray.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), best_angle, 1.0)
    return cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
```

#### B5.8 `app/ocr/engine.py`: calling Tesseract

`image_to_data` (not `image_to_string`) gives every word **with its box and confidence**, which the table parser
needs. `--oem 1` is the neural (LSTM) engine. `--psm 6` (setting `OCR_PSM`) treats the page as one block of text;
if one supplier's bills read badly, try 4 or 11.

**Whole file** (81 lines): `backend/app/ocr/engine.py`

```python
"""Tesseract: a cleaned image → words with their boxes.

Tesseract is a separate program (tesseract.exe), not a Python package. Where it is looked for:
    1. TESSERACT_CMD in backend.env / .env (full path to tesseract.exe)
    2. resources\\tesseract\\tesseract.exe in the installed app (bundled by electron-builder)
    3. "tesseract" on PATH (a developer PC with Tesseract installed)
"""
from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

import numpy as np
import pytesseract
from flask import current_app
from pytesseract import Output

from app.errors.exceptions import BadRequestError
from app.ocr import Word
from app.utils.paths import is_frozen


def _bundled_dir() -> Path | None:
    """resources\\tesseract, next to resources\\backend (where literetailer-backend.exe is)."""
    if not is_frozen():
        return None
    folder = Path(sys.executable).resolve().parent.parent / "tesseract"
    return folder if (folder / "tesseract.exe").exists() else None


def _setup() -> None:
    configured = current_app.config.get("TESSERACT_CMD")
    bundled = _bundled_dir()
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured
    elif bundled:
        pytesseract.pytesseract.tesseract_cmd = str(bundled / "tesseract.exe")
        os.environ.setdefault("TESSDATA_PREFIX", str(bundled / "tessdata"))


@functools.lru_cache(maxsize=1)
def _version() -> str | None:
    """Asked once per server start (it runs tesseract.exe): restart the server after installing Tesseract."""
    try:
        return str(pytesseract.get_tesseract_version())
    except Exception:
        return None


def is_available() -> bool:
    _setup()
    return _version() is not None


def read_words(image: np.ndarray, timeout: int) -> list[Word]:
    _setup()
    cfg = current_app.config
    try:
        data = pytesseract.image_to_data(
            image,
            lang=cfg["OCR_LANGUAGES"],
            config=f"--oem 1 --psm {cfg['OCR_PSM']}",  # oem 1 = the LSTM (neural) engine
            output_type=Output.DICT,
            timeout=timeout,
        )
    except pytesseract.TesseractError as exc:
        raise BadRequestError(f"Tesseract could not read the bill: {exc.message}") from exc
    except RuntimeError as exc:  # pytesseract's timeout
        raise BadRequestError("Reading the bill took too long. Try a clearer photo or fewer pages.") from exc

    words = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:  # conf -1 = a block/line marker, not a word
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(Word(text, float(x), float(y), float(x + w), float(y + h), conf))
    return words
```

### B6. Schemas: `backend/app/schemas/purchase_schemas.py`

Two changes: each Direct purchase line can carry the bill's text (`bill_description`), and three new response
models are added for the draft. The money fields of the draft are `float` so the screen receives numbers.

File: `backend/app/schemas/purchase_schemas.py`. **2 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 306**, which is:

```python
        return self
```

add these lines:

```python


# ── Reading the supplier's bill (POST /purchases/direct/extract) ───────────────

class BillProductOut(BaseModel):
    """A product for a bill line; same fields as a row of the product search on the Purchases page."""
    id: int
    name: str
    sku: str | None
    price: float | None  # last purchase cost
    selling: float | None  # selling price, before GST
    tax_rate: float
    score: int | None = None  # how close the name is (0-100); None when matched another way


class BillLineOut(BaseModel):
    description: str  # as printed on the bill
    hsn_code: str | None
    qty: float | None  # free units included
    free_qty: float | None
    unit_price: float | None  # what goes in "Rate on bill": after discount, before GST, spread over the free units
    bill_rate: float | None  # the rate printed on the bill
    discount: float | None
    tax_rate: float | None
    mrp: float | None
    batch_number: str | None
    expiry_date: date | None
    amount: float | None
    status: Literal["matched", "check", "not_found"]
    product: BillProductOut | None
    match_source: str | None  # alias / supplier_code / barcode / name
    candidates: list[BillProductOut]
    # rate_from_amount, qty_from_amount, math_mismatch, amount_missing, bad_gst, hard_to_read, mrp_below_rate
    problems: list[str]
    confidence: int  # OCR confidence 0-100 (100 for a digital PDF)


class BillExtractOut(BaseModel):
    source: Literal["pdf_text", "ocr"]
    supplier_id: int | None
    supplier_name: str | None
    gstin: str | None
    invoice_number: str | None
    invoice_date: date | None
    taxable_total: float | None
    cgst: float | None
    sgst: float | None
    igst: float | None
    round_off: float | None
    grand_total: float | None
    lines_total: float | None  # the lines' amounts added up
    lines: list[BillLineOut]
    # no_lines, lines_total_mismatch, bill_totals_mismatch, pages_skipped, used_template
    warnings: list[str]
```

**Change 2: after line 283**, which is:

```python
    to_shop: bool = False  # False = into the godown (the default when the godown is on); True = straight on the shelf
```

add these lines:

```python
    # The line's text as printed on the bill, when it was read from the bill: remembered for this supplier.
    bill_description: str | None = Field(None, max_length=300)
```

### B7. Services

#### B7.1 `app/services/bill_matching_service.py` (new): bill lines → products

Order: (1) **alias**, what this supplier's bill said before, (2) the supplier's **item code**
(`supplier_products.supplier_product_code`), (3) a **barcode** printed on the line, (4) the closest **name**.
Name matching takes the better of two scores: words in any order (`token_set_ratio`) and the sound-alike key
(`search_key`, which also handles Marathi). Products already bought from this supplier get +5.

- score ≥ 90 **and** at least 5 ahead of the next best → *matched*
- score ≥ 70 → *check* (yellow, top 3 suggestions shown)
- otherwise → *not found* (red panel)

Two equally good names (e.g. "Tata Salt Iodised 1kg" and "Tata Salt Lite 1kg" for "TATA SALT 1KG") always give
*check*, never a guess.

**Whole file** (132 lines): `backend/app/services/bill_matching_service.py`

```python
"""Bill lines → our products, first match wins:

    1. alias          this supplier's bill said exactly this before (supplier_item_aliases)
    2. supplier_code  the supplier's item code printed on the line (supplier_products.supplier_product_code)
    3. barcode        an EAN printed on the line
    4. name           closest product name (rapidfuzz), in English letters or sound-alike (search_key)

remember() saves 1. when a bill is saved, so each supplier's bills match better over time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process
from sqlalchemy import select

from app.extensions import db
from app.models.product import Product, ProductBarcode
from app.models.supplier_item_alias import SupplierItemAlias
from app.models.supplier_product import SupplierProduct
from app.utils.search_key import search_key

SURE = 90  # name score taken as the right product ...
MIN_GAP = 5  # ... when the next best is at least this far behind
POSSIBLE = 70  # below this: "not found"
LINKED_BONUS = 5  # products already bought from this supplier


@dataclass
class Match:
    status: str  # matched / check / not_found
    product: Product | None = None
    source: str | None = None
    candidates: list[tuple[Product, int]] = field(default_factory=list)  # (product, score), best first


@dataclass
class _Catalog:
    """Everything needed to match one bill, loaded once."""
    products: list[Product]
    by_id: dict[int, Product]
    names: list[str]
    keys: list[str]
    aliases: dict[str, int]
    codes: dict[str, int]
    linked: set[int]


def _catalog(supplier_id: int | None, store_id: int) -> _Catalog:
    products = list(db.session.scalars(
        select(Product).where(Product.is_active.is_(True),
                              (Product.store_id == store_id) | (Product.store_id.is_(None)))
    ))
    aliases: dict[str, int] = {}
    codes: dict[str, int] = {}
    linked: set[int] = set()
    if supplier_id:
        aliases = {a.description_key: a.product_id for a in db.session.scalars(
            select(SupplierItemAlias).where(SupplierItemAlias.supplier_id == supplier_id))}
        for sp in db.session.scalars(select(SupplierProduct).where(
                SupplierProduct.supplier_id == supplier_id, SupplierProduct.is_active.is_(True))):
            linked.add(sp.product_id)
            if sp.supplier_product_code:
                codes[sp.supplier_product_code.strip().upper()] = sp.product_id
    return _Catalog(products, {p.id: p for p in products}, [p.name.lower() for p in products],
                    [p.search_key or "" for p in products], aliases, codes, linked)


def match_lines(supplier_id: int | None, store_id: int, descriptions: list[str]) -> list[Match]:
    if not descriptions:
        return []
    catalog = _catalog(supplier_id, store_id)
    return [_match_one(d, catalog) for d in descriptions]


def _match_one(description: str, c: _Catalog) -> Match:
    pid = c.aliases.get(search_key(description))
    if pid in c.by_id:
        return Match("matched", c.by_id[pid], "alias")

    for token in re.findall(r"[A-Za-z0-9\-]+", description):
        pid = c.codes.get(token.upper())
        if pid in c.by_id:
            return Match("matched", c.by_id[pid], "supplier_code")

    for token in re.findall(r"\b\d{8,14}\b", description):
        pid = db.session.scalar(select(ProductBarcode.product_id).where(ProductBarcode.barcode == token))
        if pid in c.by_id:
            return Match("matched", c.by_id[pid], "barcode")

    if not c.products:
        return Match("not_found")
    scores: dict[int, float] = {}
    for _, score, i in process.extract(description.lower(), c.names, scorer=fuzz.token_set_ratio, limit=5):
        scores[i] = max(scores.get(i, 0), score)
    key = search_key(description)
    if key:
        for _, score, i in process.extract(key, c.keys, scorer=fuzz.ratio, limit=5):
            scores[i] = max(scores.get(i, 0), score)
    ranked = sorted(
        ((c.products[i], int(min(100, s + (LINKED_BONUS if c.products[i].id in c.linked else 0))))
         for i, s in scores.items()),
        key=lambda pair: -pair[1],
    )[:3]
    best = ranked[0][1] if ranked else 0
    second = ranked[1][1] if len(ranked) > 1 else 0
    if best >= SURE and best - second >= MIN_GAP:
        return Match("matched", ranked[0][0], "name", ranked)
    if best >= POSSIBLE:
        return Match("check", ranked[0][0], "name", ranked)
    return Match("not_found", candidates=ranked)


def remember(supplier_id: int, pairs: list[tuple[str, int]]) -> None:
    """(text on the bill, product chosen) for each saved line. Runs inside the caller's transaction."""
    latest: dict[str, tuple[str, int]] = {}
    for description, product_id in pairs:
        key = search_key(description)[:400]
        if key:
            latest[key] = (description.strip()[:300], product_id)
    for key, (description, product_id) in latest.items():
        alias = db.session.scalar(select(SupplierItemAlias).where(
            SupplierItemAlias.supplier_id == supplier_id, SupplierItemAlias.description_key == key))
        if alias:
            alias.product_id = product_id
            alias.description = description
            alias.times_used += 1
        else:
            db.session.add(SupplierItemAlias(supplier_id=supplier_id, description_key=key,
                                             description=description, product_id=product_id, times_used=1))
    db.session.flush()
```

#### B7.2 `app/services/bill_ocr_service.py` (new): the whole pipeline

- At most **2 bills are read at once** (`_slots`). Reading a photo keeps a CPU core busy for several seconds, and
  billing on the counters must never wait.
- A time limit covers the whole bill (`OCR_TIMEOUT_SECONDS`). Pages not reached are reported (`pages_skipped`).
- `unit_price` is what goes into "Rate on bill": after any discount, before GST, and spread over free units
  (10 + 1 free at ₹100 → 11 at ₹90.91). Stock cost then comes out right.
- Problems and warnings are returned as **codes**; the screen shows them in English or Marathi.

**Whole file** (262 lines): `backend/app/services/bill_ocr_service.py`

```python
"""Supplier bill (PDF or photo) → a draft for the Direct purchase screen, which a person checks and saves.

    digital PDF ──────────────► words (exact)
    scanned PDF / photo ──► image ──► cleaned ──► Tesseract ──► words
    words ──► header (GSTIN, invoice no, date, totals) + item lines ──► checks ──► products matched

Nothing is saved here except the supplier's column layout (supplier_bill_templates).
"""
from __future__ import annotations

import logging
import threading
import time
from decimal import ROUND_HALF_UP, Decimal

from flask import current_app
from PIL import UnidentifiedImageError
from sqlalchemy import func, select
from werkzeug.datastructures import FileStorage

from app.errors.exceptions import BadRequestError
from app.extensions import db
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_bill_template import SupplierBillTemplate
from app.ocr import Page, engine, header_parser, pdf_text, preprocess, rasterize, table_parser
from app.ocr.normalize import taxable_value
from app.ocr.table_parser import RawLine
from app.schemas.purchase_schemas import BillExtractOut, BillLineOut, BillProductOut
from app.services import bill_matching_service
from app.services.bill_matching_service import Match
from app.utils.transactions import transaction

log = logging.getLogger(__name__)

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/bmp"}
_GST_RATES = {Decimal(r) for r in ("0", "0.25", "1.5", "3", "5", "12", "18", "28", "40")}
_LOW_CONFIDENCE = 60
_CENT, _MILLI = Decimal("0.01"), Decimal("0.001")
# Reading a photo keeps a CPU core busy for seconds: at most two at once, so billing never waits.
_slots = threading.BoundedSemaphore(2)


def extract_bill(file: FileStorage | None, store_id: int, supplier_id: int | None = None) -> BillExtractOut:
    if file is None or not file.filename:
        raise BadRequestError("Choose the bill (PDF or photo) first.")
    data = file.read()
    if len(data) > current_app.config["UPLOAD_MAX_BYTES"]:
        raise BadRequestError("The file is too big.")
    if not _slots.acquire(timeout=30):
        raise BadRequestError("Another bill is being read. Try again in a few seconds.")
    try:
        pages, skipped = _read_pages(data, file.mimetype)
    finally:
        _slots.release()
    return _draft(pages, skipped, store_id, supplier_id)


# ── 1. File → pages of words ─────────────────────────────────────────────────

def _read_pages(data: bytes, mimetype: str | None) -> tuple[list[Page], bool]:
    """(pages, True when the time ran out before the last page)."""
    cfg = current_app.config
    is_photo = False
    if pdf_text.is_pdf(data):
        try:
            pages = pdf_text.read_text_pages(data, cfg["OCR_MAX_PAGES"])
        except Exception:
            log.warning("Bill PDF: its text could not be read, trying OCR", exc_info=True)
            pages = None
        if pages:
            return pages, False
        try:
            images = rasterize.pdf_to_images(data, cfg["OCR_MAX_PAGES"])
        except Exception as exc:
            raise BadRequestError("This PDF can't be opened.") from exc
    elif mimetype in _IMAGE_TYPES:
        try:
            images = [rasterize.load_image(data)]
        except (UnidentifiedImageError, OSError) as exc:
            raise BadRequestError("This picture can't be opened.") from exc
        is_photo = True
    else:
        raise BadRequestError("Only PDF, JPG, PNG, WEBP or TIFF bills can be read.")

    if not engine.is_available():
        raise BadRequestError("Bill reading (Tesseract) is not installed on the Main PC.")
    deadline = time.monotonic() + cfg["OCR_TIMEOUT_SECONDS"]
    pages = []
    for image in images:
        remaining = int(deadline - time.monotonic())
        if remaining < 5:
            break
        clean = preprocess.prepare(image, is_photo=is_photo)
        words = engine.read_words(clean, timeout=remaining)
        pages.append(Page(width=float(clean.shape[1]), height=float(clean.shape[0]), words=words, source="ocr"))
    if not pages:
        raise BadRequestError("Reading the bill took too long. Try a clearer photo or fewer pages.")
    return pages, len(pages) < len(images)


# ── 2. Pages → draft ─────────────────────────────────────────────────────────

def _draft(pages: list[Page], skipped: bool, store_id: int, supplier_id: int | None) -> BillExtractOut:
    text_lines = [row.text for page in pages for row in table_parser.group_rows(page.words)]
    header = header_parser.parse(text_lines)
    supplier = db.session.get(Supplier, supplier_id) if supplier_id else _supplier_by_gstin(header.gstins)
    template = (db.session.scalar(select(SupplierBillTemplate).where(SupplierBillTemplate.supplier_id == supplier.id))
                if supplier else None)

    raw: list[RawLine] = []
    layout_found = None
    used_template = False
    for number, page in enumerate(pages, start=1):
        lines, layout = table_parser.parse_page(page, number, template.columns if template else None)
        raw += lines
        if layout:
            layout_found = layout_found or layout
        elif lines:
            used_template = True
    if supplier and (layout_found or used_template):
        _save_template(supplier.id, layout_found)

    matches = bill_matching_service.match_lines(supplier.id if supplier else None, store_id,
                                                [line.description for line in raw])
    lines_out = [_line_out(line, match) for line, match in zip(raw, matches)]
    lines_total = sum((Decimal(str(l.amount)) for l in lines_out if l.amount is not None), Decimal("0"))

    warnings = []
    if not lines_out:
        warnings.append("no_lines")
    if skipped:
        warnings.append("pages_skipped")
    if used_template:
        warnings.append("used_template")
    warnings += _total_checks(header, lines_total if lines_out else None)

    gstin = None
    if supplier and supplier.gstin and supplier.gstin.upper() in header.gstins:
        gstin = supplier.gstin.upper()
    elif header.gstins:
        gstin = header.gstins[0]
    return BillExtractOut(
        source=pages[0].source,
        supplier_id=supplier.id if supplier else None,
        supplier_name=supplier.company_name if supplier else None,
        gstin=gstin,
        invoice_number=header.invoice_number,
        invoice_date=header.invoice_date,
        taxable_total=_f(header.taxable_total),
        cgst=_f(header.cgst),
        sgst=_f(header.sgst),
        igst=_f(header.igst),
        round_off=_f(header.round_off),
        grand_total=_f(header.grand_total),
        lines_total=_f(lines_total) if lines_out else None,
        lines=lines_out,
        warnings=warnings,
    )


def _supplier_by_gstin(gstins: list[str]) -> Supplier | None:
    """The bill shows the supplier's GSTIN and the store's: the one that belongs to a supplier is theirs."""
    if not gstins:
        return None
    return db.session.scalar(
        select(Supplier).where(func.upper(Supplier.gstin).in_(gstins), Supplier.is_active.is_(True)).limit(1))


def _save_template(supplier_id: int, layout: list[dict] | None) -> None:
    """A header was read: keep its layout. Only the template was used: count it."""
    with transaction():
        template = db.session.scalar(
            select(SupplierBillTemplate).where(SupplierBillTemplate.supplier_id == supplier_id))
        if template is None:
            db.session.add(SupplierBillTemplate(supplier_id=supplier_id, columns=layout, times_used=0))
        elif layout:
            template.columns = layout
        else:
            template.times_used += 1


def _line_out(line: RawLine, match: Match) -> BillLineOut:
    problems = []
    qty, rate, amount = line.qty, line.rate, line.amount
    if rate is None and qty and amount is not None:
        rate = amount / qty
        problems.append("rate_from_amount")
    if qty is None and rate and amount is not None:
        qty = (amount / rate).quantize(_MILLI, ROUND_HALF_UP)
        problems.append("qty_from_amount")

    taxable = None
    if qty and rate is not None and amount is not None:
        taxable = taxable_value(qty, rate, amount, line.discount, line.gst)
        if taxable is None and "rate_from_amount" not in problems and "qty_from_amount" not in problems:
            problems.append("math_mismatch")
    elif amount is None:
        problems.append("amount_missing")

    total_qty = (qty or Decimal("0")) + (line.free_qty or Decimal("0"))
    unit_price = None
    if total_qty and (taxable is not None or (qty and rate is not None)):
        base = taxable if taxable is not None else qty * rate
        unit_price = (base / total_qty).quantize(_CENT, ROUND_HALF_UP)  # free units lower the cost of each

    gst = line.gst
    if gst is not None and gst not in _GST_RATES:
        problems.append("bad_gst")
        gst = None
    if line.mrp is not None and unit_price is not None and line.mrp < unit_price:
        problems.append("mrp_below_rate")
    if line.confidence < _LOW_CONFIDENCE:
        problems.append("hard_to_read")

    status = match.status
    if status == "matched" and problems:
        status = "check"
    return BillLineOut(
        description=line.description,
        hsn_code=line.hsn,
        qty=_f(total_qty.quantize(_MILLI)) if total_qty else None,
        free_qty=_f(line.free_qty),
        unit_price=_f(unit_price),
        bill_rate=_f(rate.quantize(_CENT, ROUND_HALF_UP)) if rate is not None else None,
        discount=_f(line.discount),
        tax_rate=_f(gst),
        mrp=_f(line.mrp),
        batch_number=line.batch[:100] if line.batch else None,
        expiry_date=line.expiry,
        amount=_f(amount),
        status=status,
        product=_product_out(match.product) if match.product else None,
        match_source=match.source,
        candidates=[_product_out(p, score) for p, score in match.candidates],
        problems=problems,
        confidence=int(line.confidence),
    )


def _total_checks(header: header_parser.BillHeader, lines_total: Decimal | None) -> list[str]:
    warnings = []
    if lines_total is not None:
        printed = [t for t in (header.taxable_total, header.grand_total) if t is not None]
        tolerance = max(Decimal("2"), lines_total * Decimal("0.005"))
        if printed and all(abs(lines_total - t) > tolerance for t in printed):
            warnings.append("lines_total_mismatch")
    if header.grand_total is not None and header.taxable_total is not None:
        taxes = sum((t for t in (header.cgst, header.sgst, header.igst, header.round_off) if t is not None),
                    Decimal("0"))
        if abs(header.taxable_total + taxes - header.grand_total) > 2:
            warnings.append("bill_totals_mismatch")
    return warnings


def _product_out(p: Product, score: int | None = None) -> BillProductOut:
    return BillProductOut(id=p.id, name=p.name, sku=p.sku, price=_f(p.cost_price), selling=_f(p.price),
                          tax_rate=float(p.tax_rate or 0), score=score)


def _f(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None
```

#### B7.3 `app/services/direct_purchase_service.py`: remember the names when the bill is saved

This runs inside the existing transaction, so the aliases are saved only if the whole bill is saved.

File: `backend/app/services/direct_purchase_service.py`. **2 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 89** (the empty line below line 88). Line 88 is:

```python
        ), file, actor)
```

add these lines:

```python
        # 5. Lines read from the bill: remember what this supplier calls each product, for their next bill.
        bill_matching_service.remember(
            data.supplier_id, [(line.bill_description, line.product_id) for line in data.items if line.bill_description]
        )
```

**Change 2: replace line 25**:

```python
from app.services import audit_service, purchase_service, supplier_invoice_service
```

with:

```python
from app.services import audit_service, bill_matching_service, purchase_service, supplier_invoice_service
```

### B8. Routes

#### B8.1 `app/routes/purchase_routes.py`: the new endpoint

`POST /api/v1/purchases/direct/extract`, multipart form: `file`, `store_id`, optional `supplier_id`. It needs the
same permission as Direct purchase (`purchases.receive`) and checks store access.

File: `backend/app/routes/purchase_routes.py`. **2 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 89** (the empty line below line 87). Line 87 is:

```python
    }), 201
```

add these lines:

```python
@purchase_bp.post("/purchases/direct/extract")
@require_permission("purchases.receive")
def extract_direct_purchase_bill():
    """Reads the supplier's bill and returns a draft to check. Saves nothing.
    multipart/form-data: 'file' = the bill (PDF or photo), 'store_id', 'supplier_id' (optional: found from the GSTIN)."""
    actor = _current_user()
    store_id = request.form.get("store_id", type=int)
    if not store_id:
        raise BadRequestError("Choose the store first.")
    require_store_access(actor, store_id)
    draft = bill_ocr_service.extract_bill(
        request.files.get("file"), store_id, request.form.get("supplier_id", type=int)
    )
    return jsonify(draft.model_dump(mode="json")), 200
```

**Change 2: replace line 19**:

```python
from app.services import direct_purchase_service, po_pdf, po_sending_service, purchase_service
```

with:

```python
from app.services import bill_ocr_service, direct_purchase_service, po_pdf, po_sending_service, purchase_service
```

#### B8.2 `app/routes/health_routes.py`: is Tesseract installed?

`/api/v1/health` will show `"bill_reading": "up"` or `"not_installed"`. The check runs `tesseract --version` only
once per server start (cached), so the counters' frequent health checks cost nothing.

File: `backend/app/routes/health_routes.py`. **2 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 24**, which is:

```python
        "database": database,
```

add these lines:

```python
        "bill_reading": "up" if engine.is_available() else "not_installed",  # Tesseract, for Direct purchase
```

**Change 2: after line 7**, which is:

```python
from app.extensions import db
```

add these lines:

```python
from app.ocr import engine
```

### B9. Tests

The unit tests need no Tesseract and no database. The integration tests make a **digital PDF bill with fpdf2**
(already a dependency). `test_photo_read_by_tesseract` also turns it into a tilted JPEG photo and reads it with real
Tesseract; it skips itself where Tesseract isn't installed (CI), and the others run everywhere.

**Whole file** (143 lines): `backend/tests/unit/test_bill_ocr_parsing.py`

```python
"""Bill reading without Tesseract: numbers, dates, GSTINs and the table logic on hand-made word boxes."""
from datetime import date
from decimal import Decimal

from app.ocr import Page, Word
from app.ocr import header_parser, normalize, table_parser


# ── normalize ─────────────────────────────────────────────────────────────────

def test_numbers_indian_format_and_ocr_mixups():
    assert normalize.to_decimal("1,24,500.00") == Decimal("124500.00")
    assert normalize.to_decimal("24.50/-") == Decimal("24.50")
    assert normalize.to_decimal("1O") == Decimal("10")
    assert normalize.to_decimal("₹ 99") == Decimal("99")
    assert normalize.to_decimal("10 PCS") == Decimal("10")
    assert normalize.to_decimal("24,50") == Decimal("24.50")
    assert normalize.to_decimal("SALT") is None
    assert normalize.to_decimal("") is None


def test_qty_with_free():
    assert normalize.parse_qty("10+1") == (Decimal("10"), Decimal("1"))
    assert normalize.parse_qty("12") == (Decimal("12"), None)


def test_dates_and_expiry():
    assert normalize.parse_date("15/11/2026") == date(2026, 11, 15)
    assert normalize.parse_date("15-Nov-26") == date(2026, 11, 15)
    assert normalize.parse_date("31/02/2026") is None
    assert normalize.parse_expiry("10/27") == date(2027, 10, 31)
    assert normalize.parse_expiry("FEB-28") == date(2028, 2, 29)


def test_hsn():
    assert normalize.clean_hsn("2501") == "2501"
    assert normalize.clean_hsn("25O1") == "2501"
    assert normalize.clean_hsn("12") is None


def test_taxable_value_with_discount_and_gst():
    d = Decimal
    assert normalize.taxable_value(d(10), d("24.50"), d("245.00"), None, None) == d("245.00")
    assert normalize.taxable_value(d(10), d(100), d(980), d(2), None) == d(980)          # 2 % discount
    assert normalize.taxable_value(d(10), d(100), d(1050), None, d(5)) == d(1000)        # amount incl. 5 % GST
    assert normalize.taxable_value(d(10), d(100), d(1500), None, d(5)) is None           # misread


# ── header ────────────────────────────────────────────────────────────────────

def test_gstin_checksum_and_ocr_fix():
    assert header_parser.gstin_checksum_ok("27AAPFU0939F1ZV")
    assert not header_parser.gstin_checksum_ok("27AAPFU0939F1ZW")
    # O read for 0 and 2 read for Z: put right by place
    assert header_parser.find_gstins(["GSTIN: 27AAPFUO939F12V"]) == ["27AAPFU0939F1ZV"]


def test_header_fields():
    lines = [
        "SHREE TRADERS",
        "GSTIN: 27AAPFU0939F1ZV",
        "Invoice No. : GT/2311  Date: 15/11/2026",
        "Sr Description Qty Rate Amount",
        "1 TATA SALT 1KG 10 24.50 245.00",
        "Sub Total 245.00",
        "CGST @ 2.5% 6.13",
        "SGST @ 2.5% 6.13",
        "Round Off -0.26",
        "Grand Total 257.00",
    ]
    h = header_parser.parse(lines)
    assert h.gstins == ["27AAPFU0939F1ZV"]
    assert h.invoice_number == "GT/2311"
    assert h.invoice_date == date(2026, 11, 15)
    assert h.taxable_total == Decimal("245.00")
    assert h.cgst == Decimal("6.13")
    assert h.grand_total == Decimal("257.00")


def test_invoice_number_label_variants():
    assert header_parser.parse(["Invoice Number: A-77"]).invoice_number == "A-77"
    assert header_parser.parse(["Bill No 1234"]).invoice_number == "1234"


# ── table ─────────────────────────────────────────────────────────────────────

def _row(y, *cells):
    """cells = (x, text); every word 10 high, 8 wide per letter."""
    return [Word(text, x, y, x + 8 * len(text), y + 10, 90) for x, text in cells]


def _bill_page():
    words = (
        _row(20, (10, "Invoice"), (80, "No:"), (120, "A-1"))
        + _row(60, (10, "Sr"), (30, "No"), (60, "Item"), (100, "Name"), (300, "HSN"), (380, "Qty"),
               (440, "Rate"), (500, "GST%"), (560, "Amount"))
        + _row(80, (10, "1"), (60, "TATA"), (100, "SALT"), (140, "1KG"), (300, "2501"), (380, "10"),
               (440, "24.50"), (500, "0"), (560, "245.00"))
        # a long name: "OIL" is past halfway to the HSN header, but still part of the name
        + _row(100, (10, "2"), (60, "FORTUNE"), (130, "SOYABEAN"), (210, "OIL"), (300, "1507"), (380, "5+1"),
               (440, "150.00"), (500, "5"), (560, "787.50"))
        + _row(115, (60, "1L"))  # name went on to a second line
        + _row(140, (60, "Total"), (380, "16"), (560, "1032.50"))
        + _row(160, (60, "Thank"), (110, "you"))
    )
    return Page(width=700, height=300, words=words)


def test_table_rows_columns_wrap_and_end():
    lines, layout = table_parser.parse_page(_bill_page(), 1)
    assert [l.description for l in lines] == ["TATA SALT 1KG", "FORTUNE SOYABEAN OIL 1L"]
    salt, oil = lines
    assert (salt.hsn, salt.qty, salt.rate, salt.gst, salt.amount) == ("2501", 10, Decimal("24.50"), 0, Decimal("245.00"))
    assert (oil.hsn, oil.qty, oil.free_qty, oil.amount) == ("1507", 5, 1, Decimal("787.50"))
    fields = [c["field"] for c in layout]
    assert fields == ["_skip", "name", "hsn", "qty", "rate", "gst", "amount"]


def test_speck_in_header_and_serial_in_name():
    """Real OCR of a photo: a "_" speck between "Sr" and "Description" glued them into one column, so the serial
    numbers ended up in the item names."""
    words = (
        _row(60, (10, "Sr"), (30, "_"), (45, "Description"), (300, "HSN"), (380, "Qty"), (440, "Rate"), (560, "Amount"))
        + _row(80, (10, "1"), (45, "TATA"), (85, "SALT"), (300, "2501"), (380, "10"), (440, "24.50"), (560, "245.00"))
        + _row(100, (10, "2"), (45, "7UP"), (80, "2L"), (300, "2202"), (380, "6"), (440, "80.00"), (560, "480.00"))
    )
    lines, layout = table_parser.parse_page(Page(width=700, height=300, words=words), 1)
    assert [c["field"] for c in layout][:2] == ["_skip", "name"]
    assert [l.description for l in lines] == ["TATA SALT", "7UP 2L"]
    # Sr. No. read into the name column anyway (no header column for it): taken off when it is the line's number
    words = [w for w in words if w.text not in ("Sr", "_")]
    lines, _ = table_parser.parse_page(Page(width=700, height=300, words=words), 1)
    assert [l.description for l in lines] == ["TATA SALT", "7UP 2L"]


def test_template_used_when_header_missing():
    _, layout = table_parser.parse_page(_bill_page(), 1)
    page = _bill_page()
    page.words = [w for w in page.words if not (59 <= w.y0 <= 61)]  # header row unreadable
    assert table_parser.parse_page(page, 1)[0] == []                 # no header, no template: nothing
    lines, new_layout = table_parser.parse_page(page, 1, template=layout)
    assert new_layout is None
    assert [l.description for l in lines] == ["TATA SALT 1KG", "FORTUNE SOYABEAN OIL 1L"]
```

**Whole file** (141 lines): `backend/tests/integration/test_bill_reading.py`

```python
"""Direct purchase → "Read from bill": a digital PDF bill (no Tesseract needed) becomes a draft; saving the bill
teaches the app what this supplier calls each product."""
import io
import json
from datetime import date

import pytest
from fpdf import FPDF

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.supplier import Supplier
from app.models.supplier_bill_template import SupplierBillTemplate
from app.models.supplier_item_alias import SupplierItemAlias
from tests.factories import make_product

pytestmark = pytest.mark.integration
GSTIN = "27AAPFU0939F1ZV"


@pytest.fixture
def supplier(app):
    s = Supplier(supplier_code="SUP-OCR001", company_name="Shree Traders", gstin=GSTIN,
                 payment_terms=PaymentTerms.NET_30)
    db.session.add(s)
    db.session.commit()
    return s


def _bill_pdf(*lines, number="GT/2311") -> bytes:
    """A bill as billing software prints it: header, a table, totals."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=10)
    pdf.text(10, 15, f"SHREE TRADERS   GSTIN: {GSTIN}")
    pdf.text(10, 22, f"Invoice No: {number}    Date: 15/11/2026")
    y = 35
    total = 0.0
    for cells in (("Sr", "Description", "HSN", "Qty", "Rate", "GST%", "Amount"), *lines):
        for x, text in zip((10, 20, 95, 115, 130, 150, 165), cells):
            pdf.text(x, y, text)
        if cells[0] != "Sr":
            total += float(cells[6])
        y += 7
    pdf.text(20, y, "Total")
    pdf.text(165, y, f"{total:.2f}")
    pdf.text(10, y + 10, f"Grand Total {total:.2f}")
    return bytes(pdf.output())


def _extract(client, headers, store, pdf: bytes, **form):
    data = {"file": (io.BytesIO(pdf), "bill.pdf", "application/pdf"), "store_id": str(store.id), **form}
    return client.post("/api/v1/purchases/direct/extract", data=data, headers=headers,
                       content_type="multipart/form-data")


SALT = ("1", "TATA SALT 1KG", "2501", "10", "24.50", "0", "245.00")
OIL = ("2", "FORTUNE SOYABEAN OIL 1L", "1507", "5", "150.00", "5", "787.50")


def test_digital_pdf_becomes_a_draft(client, admin_headers, store, supplier):
    make_product(store, name="Tata Salt 1kg", price="28.00", stock=0)
    resp = _extract(client, admin_headers, store, _bill_pdf(SALT, OIL))
    assert resp.status_code == 200, resp.get_json()
    d = resp.get_json()
    assert d["source"] == "pdf_text"
    assert (d["supplier_id"], d["gstin"]) == (supplier.id, GSTIN)  # found from the GSTIN
    assert (d["invoice_number"], d["invoice_date"], d["grand_total"]) == ("GT/2311", "2026-11-15", 1032.5)
    assert d["warnings"] == []

    salt, oil = d["lines"]
    assert (salt["description"], salt["qty"], salt["unit_price"], salt["hsn_code"]) == ("TATA SALT 1KG", 10, 24.5, "2501")
    assert salt["status"] == "matched" and salt["product"]["name"] == "Tata Salt 1kg"
    assert oil["unit_price"] == 150.0 and oil["tax_rate"] == 5  # 787.50 = 5 × 150 + 5 % GST
    assert oil["status"] == "not_found"  # no such product yet

    db.session.expire_all()
    assert db.session.scalar(db.select(SupplierBillTemplate).filter_by(supplier_id=supplier.id)) is not None


def test_saving_the_bill_remembers_the_supplier_name(client, admin_headers, store, supplier):
    oil = make_product(store, name="सोयाबीन तेल फॉर्च्यून 1 लिटर", price="160.00", stock=0)
    first = _extract(client, admin_headers, store, _bill_pdf(OIL)).get_json()
    assert first["lines"][0]["status"] == "not_found"  # the Marathi name doesn't look like the bill's

    body = {"supplier_id": supplier.id, "store_id": store.id, "invoice_number": "GT/2311",
            "invoice_date": str(date.today()), "grand_total": "787.50",
            "items": [{"product_id": oil.id, "qty": "5", "unit_price": "150", "tax_rate": "5",
                       "bill_description": "FORTUNE SOYABEAN OIL 1L"}]}
    saved = client.post("/api/v1/purchases/direct", headers=admin_headers, content_type="multipart/form-data",
                        data={"data": json.dumps(body), "file": (io.BytesIO(b"%PDF-1.4"), "bill.pdf", "application/pdf")})
    assert saved.status_code == 201, saved.get_json()
    assert db.session.scalar(db.select(SupplierItemAlias).filter_by(supplier_id=supplier.id)).product_id == oil.id

    again = _extract(client, admin_headers, store, _bill_pdf(OIL, number="GT/2400")).get_json()
    line = again["lines"][0]
    assert (line["status"], line["match_source"], line["product"]["id"]) == ("matched", "alias", oil.id)


def test_photo_read_by_tesseract(client, admin_headers, store, supplier):
    """The OCR path for real: the bill as a tilted phone photo (JPEG). Skipped where Tesseract isn't installed (CI)."""
    from app.ocr import engine, rasterize

    if not engine.is_available():
        pytest.skip("Tesseract is not installed")
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    from PIL import Image

    make_product(store, name="Tata Salt 1kg", price="28.00", stock=0)
    page = np.array(rasterize.pdf_to_images(_bill_pdf(SALT, OIL), 1)[0].convert("L"))
    canvas = np.full((page.shape[0] + 400, page.shape[1] + 400), 50, np.uint8)  # on a dark table
    canvas[200:200 + page.shape[0], 200:200 + page.shape[1]] = page
    turn = cv2.getRotationMatrix2D((canvas.shape[1] / 2, canvas.shape[0] / 2), 3, 1.0)  # tilted 3°
    photo = cv2.warpAffine(canvas, turn, (canvas.shape[1], canvas.shape[0]), borderValue=50)
    jpeg = io.BytesIO()
    Image.fromarray(photo).save(jpeg, format="JPEG", quality=85)

    data = {"file": (io.BytesIO(jpeg.getvalue()), "bill.jpg", "image/jpeg"), "store_id": str(store.id)}
    resp = client.post("/api/v1/purchases/direct/extract", data=data, headers=admin_headers,
                       content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    d = resp.get_json()
    assert d["source"] == "ocr"
    assert (d["supplier_id"], d["invoice_number"], d["grand_total"]) == (supplier.id, "GT/2311", 1032.5)
    salt, oil = d["lines"]
    assert (salt["description"], salt["qty"], salt["unit_price"]) == ("TATA SALT 1KG", 10, 24.5)
    assert salt["product"]["name"] == "Tata Salt 1kg"
    assert (oil["qty"], oil["unit_price"], oil["tax_rate"], oil["amount"]) == (5, 150.0, 5, 787.5)


def test_wrong_file_and_missing_store(client, admin_headers, store):
    resp = _extract(client, admin_headers, store, b"hello")
    assert resp.status_code == 400  # not a PDF, not a picture
    resp = client.post("/api/v1/purchases/direct/extract", headers=admin_headers, content_type="multipart/form-data",
                       data={"file": (io.BytesIO(b"%PDF-1.4"), "bill.pdf", "application/pdf")})
    assert resp.status_code == 400  # no store_id


def test_cashier_cannot_read_bills(client, cashier_headers, store):
    assert _extract(client, cashier_headers, store, _bill_pdf(SALT)).status_code == 403
```

Run them, then the whole suite:

```powershell
cd backend
.venv\Scripts\python -m pytest tests/unit/test_bill_ocr_parsing.py tests/integration/test_bill_reading.py -v
.venv\Scripts\python -m pytest
```

---

# Part C: Frontend

### C1. `frontend/src/services/api/purchaseApi.ts`: types and the API call

Problem and warning codes are exact union types (`BillProblem`, `BillWarning`). The app's translations are
type-checked, and ``t(`purchases.direct.problem.${code}`)`` compiles only when `code` is one of the known keys.

File: `frontend/src/services/api/purchaseApi.ts`. **3 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 163**, which is:

```ts
  },
```

add these lines:

```ts

  /** Reads the supplier's bill (PDF or photo) on the Main PC and returns a draft. Saves nothing. */
  extractBill(file: File, storeId: number, supplierId?: number) {
    const form = new FormData();
    form.append('file', file);
    form.append('store_id', String(storeId));
    if (supplierId) form.append('supplier_id', String(supplierId));
    return httpClient.post<BillExtract>('/purchases/direct/extract', form, { timeout: 120_000 });
  },
```

**Change 2: after line 75** (the empty line below line 74). Line 74 is:

```ts
}
```

add these lines:

```ts
/** A product suggested for a line read from the bill (same fields as the product search list). */
export interface BillProduct {
  id: number;
  name: string;
  sku: string | null;
  price: number | null; // last purchase cost
  selling: number | null;
  tax_rate: number;
  score: number | null; // how close the name is, 0-100
}

export type BillLineStatus = 'matched' | 'check' | 'not_found';
/** Texts: purchases.direct.problem.<code> */
export type BillProblem =
  | 'rate_from_amount' | 'qty_from_amount' | 'math_mismatch' | 'amount_missing' | 'bad_gst' | 'hard_to_read'
  | 'mrp_below_rate';
/** Texts: purchases.direct.warning.<code> */
export type BillWarning = 'no_lines' | 'lines_total_mismatch' | 'bill_totals_mismatch' | 'pages_skipped' | 'used_template';

/** One item line read from the supplier's bill. */
export interface BillLine {
  description: string;
  hsn_code: string | null;
  qty: number | null; // free units included
  free_qty: number | null;
  unit_price: number | null; // goes in "Rate on bill": after discount, before GST
  bill_rate: number | null;
  discount: number | null;
  tax_rate: number | null;
  mrp: number | null;
  batch_number: string | null;
  expiry_date: string | null;
  amount: number | null;
  status: BillLineStatus;
  product: BillProduct | null;
  match_source: string | null;
  candidates: BillProduct[];
  problems: BillProblem[];
  confidence: number;
}

/** What "Read from bill" found. Nothing is saved until the bill is saved as usual. */
export interface BillExtract {
  source: 'pdf_text' | 'ocr';
  supplier_id: number | null;
  supplier_name: string | null;
  gstin: string | null;
  invoice_number: string | null;
  invoice_date: string | null;
  taxable_total: number | null;
  cgst: number | null;
  sgst: number | null;
  igst: number | null;
  round_off: number | null;
  grand_total: number | null;
  lines_total: number | null;
  lines: BillLine[];
  warnings: BillWarning[];
}
```

**Change 3: after line 72**, which is:

```ts
    to_shop: boolean;
```

add these lines:

```ts
    bill_description?: string | null; // the line as printed on the bill (read from it): remembered for the supplier
```

### C2. Texts: `frontend/src/i18n/locales/en.ts` and `mr.ts`

Both files get the same keys inside `purchases.direct`, after `removeLine` (line 1315 in both). `mr.ts` is typed
`typeof en`, so a key missing from one of them fails the typecheck.

File: `frontend/src/i18n/locales/en.ts`. **1 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 1315**, which is:

```ts
      removeLine: 'Remove line',
```

add these lines:

```ts
      readBill: 'Read from bill',
      reading: 'Reading the bill…',
      readHint: 'Fills the form from the bill. Check every line before saving.',
      readNeedsStore: 'Choose the store first, then read the bill.',
      onBill: 'On bill',
      looksRight: 'Looks right',
      unmatchedTitle: '{{count}} line(s) from the bill need a product',
      unmatchedHint: 'Click the right product, or "Choose another" and pick it in the search below. The bill\'s name for it is remembered for next time.',
      pickOther: 'Choose another…',
      pickingNow: 'Now pick it in the search ↓',
      skipLine: 'Leave this line out',
      problem: {
        rate_from_amount: 'Rate not read; worked out from the amount.',
        qty_from_amount: 'Quantity not read; worked out from the amount.',
        math_mismatch: 'Quantity × rate does not match the amount on the bill.',
        amount_missing: 'Amount not read.',
        bad_gst: 'The GST % read is not a GST rate.',
        hard_to_read: 'Hard to read on the bill.',
        mrp_below_rate: 'MRP is below the rate. Check both.',
      },
      warning: {
        no_lines: 'No item lines were found. Enter them by hand, or try a clearer photo.',
        lines_total_mismatch: 'The lines add up to ₹{{lines}} but the bill total is ₹{{bill}}. A line may be missing or misread.',
        bill_totals_mismatch: 'The totals printed on the bill do not add up. Check the bill total.',
        pages_skipped: 'Only the first pages were read (time limit). Add the other lines by hand.',
        used_template: 'The table header could not be read; this supplier\'s saved layout was used.',
      },
```

File: `frontend/src/i18n/locales/mr.ts`. **1 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 1315**, which is:

```ts
      removeLine: 'ओळ काढा',
```

add these lines:

```ts
      readBill: 'बिलातून वाचा',
      reading: 'बिल वाचत आहे…',
      readHint: 'बिलावरून फॉर्म भरला जातो. जतन करण्यापूर्वी प्रत्येक ओळ तपासा.',
      readNeedsStore: 'आधी दुकान निवडा, मग बिल वाचा.',
      onBill: 'बिलावर',
      looksRight: 'बरोबर आहे',
      unmatchedTitle: 'बिलातील {{count}} ओळींसाठी उत्पादन निवडा',
      unmatchedHint: 'योग्य उत्पादनावर क्लिक करा, किंवा "दुसरे निवडा" दाबून खालील शोधात निवडा. बिलावरील नाव पुढच्या वेळेसाठी लक्षात ठेवले जाते.',
      pickOther: 'दुसरे निवडा…',
      pickingNow: 'आता खालील शोधात निवडा ↓',
      skipLine: 'ही ओळ वगळा',
      problem: {
        rate_from_amount: 'दर वाचता आला नाही; रकमेवरून काढला.',
        qty_from_amount: 'प्रमाण वाचता आले नाही; रकमेवरून काढले.',
        math_mismatch: 'प्रमाण × दर बिलावरील रकमेशी जुळत नाही.',
        amount_missing: 'रक्कम वाचता आली नाही.',
        bad_gst: 'वाचलेला GST % हा GST दर नाही.',
        hard_to_read: 'बिलावर नीट वाचता येत नाही.',
        mrp_below_rate: 'MRP दरापेक्षा कमी आहे. दोन्ही तपासा.',
      },
      warning: {
        no_lines: 'एकही मालाची ओळ सापडली नाही. हाताने भरा, किंवा अधिक स्पष्ट फोटो वापरा.',
        lines_total_mismatch: 'ओळींची बेरीज ₹{{lines}} आहे पण बिलाची रक्कम ₹{{bill}} आहे. एखादी ओळ सुटली किंवा चुकीची वाचली असेल.',
        bill_totals_mismatch: 'बिलावर छापलेल्या रकमांची बेरीज जुळत नाही. बिलाची एकूण रक्कम तपासा.',
        pages_skipped: 'वेळेअभावी फक्त पहिली पाने वाचली. उरलेल्या ओळी हाताने भरा.',
        used_template: 'टेबलचे शीर्षक वाचता आले नाही; या पुरवठादाराची जतन केलेली मांडणी वापरली.',
      },
```

### C3. The screen: `frontend/src/pages/admin/PurchasesPage.tsx` (`DirectPurchaseModal`)

What changes on the screen:
- A **Read from bill** button appears once a file is chosen. It needs the store to be selected first.
- Lines read from the bill appear in the normal table. *Check* lines are yellow, show the bill's text and the
  reasons, and have a **✓ Looks right** button.
- Lines with no product appear in a red panel above the product search: click a suggestion, or **Choose
  another…** and pick in the search. Creating a **+ New product** while a line is waiting also uses that line.
- Saving sends `bill_description`, so the names are remembered.

File: `frontend/src/pages/admin/PurchasesPage.tsx`. **11 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: replace lines 2384–2385**:

```tsx
                  <tr key={l._id}>
                    <td><strong>{l.product.name}</strong></td>
```

with:

```tsx
                  <tr key={l._id} style={l.check ? { background: 'var(--warn-bg)' } : undefined}>
                    <td>
                      <strong>{l.product.name}</strong>
                      {l.billText && <div className="hint-text">{t('purchases.direct.onBill')}: {l.billText}</div>}
                      {l.problems?.map((p) => (
                        <div key={p} className="hint-text" style={{ color: 'var(--warn-text)' }}>⚠ {t(`purchases.direct.problem.${p}`)}</div>
                      ))}
                      {l.check && (
                        <button type="button" className="btn-sm" onClick={() => setLine(l._id, { check: false, problems: [] })}>
                          ✓ {t('purchases.direct.looksRight')}
                        </button>
                      )}
                    </td>
```

**Change 2: replace line 2361**:

```tsx
            onCreated={(p) => { addLine(p); setNewProductOpen(false); }} />
```

with:

```tsx
            onCreated={(p) => { pickProduct(p); setNewProductOpen(false); }} />
```

**Change 3: replace line 2352**:

```tsx
        <ProductSearch onSelect={addLine} storeId={storeId} supplierId={supplierId || undefined} />
```

with:

```tsx
        {unmatched.length > 0 && (
          <div style={{ marginBottom: 12, padding: 12, borderRadius: 8, background: 'var(--danger-bg)', border: '1px solid var(--danger-border)' }}>
            <strong>{t('purchases.direct.unmatchedTitle', { count: unmatched.length })}</strong>
            <div className="hint-text">{t('purchases.direct.unmatchedHint')}</div>
            {unmatched.map((b, i) => (
              <div key={`${i}-${b.description}`} style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', paddingTop: 8 }}>
                <span style={{ minWidth: 240 }}>
                  <strong>{b.description}</strong>
                  {b.qty != null && <> · {b.qty} × ₹{b.unit_price ?? '?'}</>}
                </span>
                {b.candidates.map((c) => (
                  <button key={c.id} type="button" className="btn-sm" onClick={() => takeBillLine(b, billProductRow(c))}>
                    {c.name}{c.score != null ? ` (${c.score}%)` : ''}
                  </button>
                ))}
                <button type="button" className="btn-sm" style={pickFor === b ? { outline: '2px solid var(--warn)' } : undefined}
                  onClick={() => setPickFor(pickFor === b ? null : b)}>
                  {pickFor === b ? t('purchases.direct.pickingNow') : t('purchases.direct.pickOther')}
                </button>
                <button type="button" className="btn-icon" title={t('purchases.direct.skipLine')}
                  onClick={() => setUnmatched((cur) => cur.filter((x) => x !== b))}>
                  <IconTrash size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        <ProductSearch onSelect={pickProduct} storeId={storeId} supplierId={supplierId || undefined} />
```

**Change 4: after line 2339**, which is:

```tsx
        </div>
```

add these lines:

```tsx
        {file && (
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 }}>
            <button type="button" className="btn-secondary" disabled={reading || storeId === ''} onClick={readBill}>
              {reading ? t('purchases.direct.reading') : t('purchases.direct.readBill')}
            </button>
            <span className="hint-text">
              {storeId === '' ? t('purchases.direct.readNeedsStore') : t('purchases.direct.readHint')}
            </span>
          </div>
        )}
        {readWarnings.length > 0 && (
          <div className="page-error" style={{ background: 'var(--warn-bg)', border: '1px solid var(--warn-border)', color: 'var(--warn-text)' }}>
            {readWarnings.map((w) => <div key={w}>{t(`purchases.direct.warning.${w}`, readTotals)}</div>)}
          </div>
        )}
```

**Change 5: replace line 2324**:

```tsx
            <select className="field-input" value={supplierId} onChange={(e) => { setSupplierId(Number(e.target.value)); setLines([]); }}>
```

with:

```tsx
            <select className="field-input" value={supplierId} onChange={(e) => { setSupplierId(Number(e.target.value)); setLines([]); setUnmatched([]); setPickFor(null); }}>
```

**Change 6: after line 2276**, which is:

```tsx
          expiry_date: l.expiry || null, to_shop: godownOn && l.toShop,
```

add these lines:

```tsx
          bill_description: l.billText ?? null,
```

**Change 7: after line 2253** (the empty line below line 2252). Line 2252 is:

```tsx
  }
```

add these lines:

```tsx
  /** "Read from bill": the Main PC reads the chosen file and the form is filled. Nothing is saved yet. */
  async function readBill() {
    if (!file || storeId === '') return;
    setReading(true);
    setErr('');
    try {
      const { data } = await purchaseApi.extractBill(file, storeId, supplierId || undefined);
      if (data.supplier_id && !supplierId) setSupplierId(data.supplier_id);
      if (data.invoice_number) setInvoiceNo(data.invoice_number);
      if (data.invoice_date) setInvoiceDate(data.invoice_date);
      if (data.grand_total != null) setBillTotal(String(data.grand_total));
      const taken = new Set(lines.map((l) => l.product.id));
      const added: DirectLine[] = [];
      const waiting: BillLine[] = [];
      for (const b of data.lines) {
        if (b.product && b.status !== 'not_found' && !taken.has(b.product.id)) {
          taken.add(b.product.id);
          added.push(lineFromBill(billProductRow(b.product), b));
        } else {
          waiting.push(b);
        }
      }
      setLines((cur) => [...cur, ...added]);
      setUnmatched(waiting);
      setReadWarnings(data.warnings);
      setReadTotals({ lines: (data.lines_total ?? 0).toFixed(2), bill: (data.grand_total ?? 0).toFixed(2) });
    } catch (e) {
      setErr(getErrorMessage(e));
    } finally {
      setReading(false);
    }
  }

  /** The product for a bill line that wasn't matched: a suggestion clicked, or picked in the search. */
  function takeBillLine(b: BillLine, p: ProductRow) {
    if (lines.some((l) => l.product.id === p.id)) {
      setErr(t('purchases.direct.twice', { name: p.name }));
      return;
    }
    setErr('');
    setLines((cur) => [...cur, lineFromBill(p, b)]);
    setUnmatched((cur) => cur.filter((x) => x !== b));
    setPickFor(null);
  }

  function pickProduct(p: ProductRow) {
    if (pickFor) takeBillLine(pickFor, p);
    else addLine(p);
  }
```

**Change 8: after line 2233**, which is:

```tsx
  const [toReview, setToReview] = useState<number[] | null>(null);
```

add these lines:

```tsx
  const [reading, setReading] = useState(false);
  const [readWarnings, setReadWarnings] = useState<BillWarning[]>([]);
  const [readTotals, setReadTotals] = useState<{ lines: string; bill: string }>({ lines: '', bill: '' });
  const [unmatched, setUnmatched] = useState<BillLine[]>([]); // bill lines still waiting for a product
  const [pickFor, setPickFor] = useState<BillLine | null>(null); // the next product picked in the search is for this line
```

**Change 9: after line 2209** (the empty line below line 2208). Line 2208 is:

```tsx
}
```

add these lines:

```tsx
function billProductRow(p: BillProduct): ProductRow {
  return { id: p.id, name: p.name, sku: p.sku, price: p.price, selling: p.selling, tax_rate: p.tax_rate };
}

/** A form line filled from a line read from the bill; the bill's values win over the product's. */
function lineFromBill(p: ProductRow, b: BillLine): DirectLine {
  const text = (v: number | string | null) => (v == null ? '' : String(v));
  return {
    _id: Date.now() + Math.random(), product: p,
    qty: text(b.qty) || '1',
    rate: b.unit_price != null ? String(b.unit_price) : text(p.price),
    gst: b.tax_rate != null ? String(b.tax_rate) : String(p.tax_rate ?? 0),
    mrp: text(b.mrp), hsn: b.hsn_code ?? '', batch: b.batch_number ?? '', expiry: b.expiry_date ?? '',
    toShop: false, billText: b.description, check: b.status !== 'matched', problems: b.problems,
  };
}
```

**Change 10: after line 2200**, which is:

```tsx
  toShop: boolean; // false = godown (default)
```

add these lines:

```tsx
  billText?: string; // the line as printed on the bill, when it was read from the bill
  check?: boolean; // read from the bill but not certain: shown yellow
  problems?: BillProblem[];
```

**Change 11: after line 17**, which is:

```tsx
import type {
```

add these lines:

```tsx
  BillLine,
  BillProblem,
  BillProduct,
  BillWarning,
```

### C4. Check

```powershell
cd frontend
npm run typecheck
npm test
```

---

# Part D: Installer (Main PC)

Tesseract is a separate program. The installer must carry it, and PyInstaller must pack the new packages' data
files.

### D1. `backend/literetailer-backend.spec`

pdfminer (inside pdfplumber) has font/cmap data files, pypdfium2 has `pdfium.dll`, and rapidfuzz has compiled parts.
OpenCV is handled by PyInstaller's own hooks.

File: `backend/literetailer-backend.spec`. **1 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: replace line 35**:

```python
            "indic_transliteration"):  # its scripts are .toml data files
```

with:

```python
            "indic_transliteration",  # its scripts are .toml data files
            "pdfminer", "pypdfium2", "pypdfium2_raw", "rapidfuzz"):  # bill reading: cmap files, pdfium.dll
```

### D2. `frontend/electron-builder.yml`

File: `frontend/electron-builder.yml`. **1 change(s).** Line numbers are those of the file *before* you change it, and the changes are listed **from the bottom of the file up**, so making them in this order keeps every number correct.

**Change 1: after line 22**, which is:

```yaml
    to: backend/winsw/LiteRetailerServer.xml
```

add these lines:

```yaml
  # Tesseract OCR (reads supplier bills on Direct purchase) -> resources\tesseract\tesseract.exe + tessdata\
  # Copied from C:\Program Files\Tesseract-OCR on the build PC (see the bill-reading guide).
  - from: build/vendor/tesseract
    to: tesseract
```

### D3. Put Tesseract in the build folder

`frontend/build/vendor/` is already in `.gitignore` (WinSW lives there too), so Tesseract is not committed. On the
build PC:

```powershell
New-Item -ItemType Directory -Force frontend\build\vendor\tesseract
Copy-Item -Recurse "C:\Program Files\Tesseract-OCR\*" frontend\build\vendor\tesseract\
# Optional, to make the installer smaller: keep only these in tessdata\
#   eng.traineddata, mar.traineddata, osd.traineddata, and the configs\ folder
```

In the installed app this becomes `resources\tesseract\tesseract.exe`, which `engine.py` finds by itself
(`_bundled_dir`) and points `TESSDATA_PREFIX` at. Tesseract's licence is Apache 2.0: keep its LICENSE file in that
folder. Expect the installer to grow by roughly 80–120 MB (Tesseract + OpenCV).

---

# Part E: Try it

1. Start the backend and the app. Open `http://<main-pc>:5000/api/v1/health` and check `"bill_reading": "up"`.
2. Purchases → **Goods arrived without PO** → choose the store → choose a bill file → **Read from bill**.
3. Start with a **digital PDF** from a distributor (instant, exact), then a **scanned PDF**, then a **phone photo**.

**If a supplier's bills read badly:**

| What you see | Try |
|---|---|
| No lines found on a photo | flatter photo, good light, the whole bill in the frame; or `OCR_PSM=4` |
| Item names cut into two columns | the header words of that supplier are missing from `HEADER_WORDS` in `table_parser.py`: add them (lower case, letters and % only) |
| Marathi item names come out as nonsense | `OCR_LANGUAGES=eng+mar` (slower) |
| "Reading the bill took too long" | `OCR_TIMEOUT_SECONDS=150`, or a smaller photo |
| Wrong GSTIN picked | add the GSTIN to the supplier in Suppliers: the one matching a supplier is used |

Debugging tip: in a Flask shell you can run the steps one by one. Example:
`from app.ocr import rasterize, preprocess, engine`, then `img = rasterize.load_image(open("bill.jpg","rb").read())`,
`clean = preprocess.prepare(img, is_photo=True)`, `cv2.imwrite("clean.png", clean)`. Look at `clean.png`: if
*you* can't read it, Tesseract can't either.

# Part F: Known limits (on purpose, for a first version)

- **Handwritten bills** are not readable by Tesseract. They stay manual.
- **Pack/case conversion** (bill says 2 cases, you stock 48 pieces) isn't done. Enter pieces and the per-piece rate.
  A later version can store "pieces per bill unit" on `supplier_item_aliases`.
- **Headers printed on two lines** ("Batch" above "No."): one-line headers work best. The saved layout helps.
- **Bills photographed sideways or upside down**: phones normally store the rotation (EXIF), which is applied.
  A picture that is really rotated needs rotating before upload; Tesseract's OSD could do this later.
- A product whose name **starts with "Total"** would end the table early.
