"""Supplier bill (PDF or photo) → a draft for the Direct purchase screen, which a person checks and saves.

    digital PDF ──────────────► words (exact)
    scanned PDF / photo ──► image ──► cleaned ──► RapidOCR (Tesseract if missing) ──► words
    words ──► header (GSTIN, invoice no, date, totals) + item lines ──► checks ──► products matched

Nothing is saved here except the supplier's column layout (supplier_bill_templates).
"""
from __future__ import annotations

import io
import logging
import re
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
from app.models.store import Store
from app.models.supplier import Supplier
from app.models.supplier_bill_template import SupplierBillTemplate
from app.ocr import Page, engine, header_parser, pdf_text, preprocess, rasterize, table_parser
from app.ocr.normalize import taxable_value, to_decimal
from app.ocr.table_parser import RawLine
from app.schemas.purchase_schemas import BillExtractOut, BillLineOut, BillProductOut
from app.services import bill_matching_service, purchase_service
from app.services.bill_matching_service import Match
from app.utils.transactions import transaction

log = logging.getLogger(__name__)

_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/tiff", "image/bmp"}
_GST_RATES = {Decimal(r) for r in ("0", "0.25", "1.5", "3", "5", "12", "18", "28", "40")}
_LOW_CONFIDENCE = 60
_CENT, _MILLI = Decimal("0.01"), Decimal("0.001")
# Reading a photo keeps a CPU core busy for seconds: at most two at once, so billing never waits.
_slots = threading.BoundedSemaphore(2)


def extract_bill(files: list[FileStorage], store_id: int, supplier_id: int | None = None) -> BillExtractOut:
    files = [f for f in files if f and f.filename]
    if not files:
        raise BadRequestError("Choose the bill (PDF or photo) first.")
    if len(files) > 1:
        _check_many(files)
    blobs = []
    for f in files:
        data = f.read()
        if len(data) > current_app.config["UPLOAD_MAX_BYTES"]:
            raise BadRequestError(f"'{f.filename}' is too big.")
        blobs.append((data, f.mimetype))
    if not _slots.acquire(timeout=30):
        raise BadRequestError("Another bill is being read. Try again in a few seconds.")
    try:
        deadline = time.monotonic() + current_app.config["OCR_TIMEOUT_SECONDS"]  # for all the photos together
        pages: list[Page] = []
        extra_lines: list[str] = []
        skipped = False
        for data, mimetype in blobs:
            if deadline - time.monotonic() < 5:
                skipped = True  # out of time: the photos left are not read
                break
            got, cut, extra = _read_pages(data, mimetype, deadline)
            pages += got
            extra_lines += extra
            skipped = skipped or cut
    finally:
        _slots.release()
    return _draft(pages, skipped, store_id, supplier_id, extra_lines)


def one_bill_file(files: list[FileStorage]) -> FileStorage | None:
    """The bill to save on the invoice: the one file chosen, or several photos joined into one PDF."""
    files = [f for f in files if f and f.filename]
    if len(files) <= 1:
        return files[0] if files else None
    _check_many(files)
    images = []
    for f in files:
        try:
            images.append(rasterize.load_image(f.read()))
        except (UnidentifiedImageError, OSError) as exc:
            raise BadRequestError(f"'{f.filename}' can't be opened.") from exc
    pdf = rasterize.images_to_pdf(images)
    return FileStorage(stream=io.BytesIO(pdf), filename="bill.pdf", content_type="application/pdf")


def _check_many(files: list[FileStorage]) -> None:
    limit = current_app.config["OCR_MAX_PAGES"]
    if len(files) > limit:
        raise BadRequestError(f"At most {limit} photos of one bill.")
    if any(f.mimetype not in _IMAGE_TYPES for f in files):
        raise BadRequestError("Several files must all be photos. Send a PDF on its own.")


# ── 1. File → pages of words ─────────────────────────────────────────────────

def _read_pages(data: bytes, mimetype: str | None, deadline: float) -> tuple[list[Page], bool, list[str]]:
    """(pages, True when the time ran out before the last page, text lines of a scanned PDF's own OCR layer).

    A scanned PDF that already carries some program's OCR text ("OCR ready") is read again by our engine: that
    text is often wrong. Its lines are kept as a second chance for the GSTIN and the invoice number."""
    cfg = current_app.config
    is_photo = False
    layer: list[Page] | None = None
    if pdf_text.is_pdf(data):
        try:
            layer = pdf_text.read_text_pages(data, cfg["OCR_MAX_PAGES"])
        except Exception:
            log.warning("Bill PDF: its text could not be read, trying OCR", exc_info=True)
        if layer and (not all(p.scan for p in layer) or not engine.is_available()):
            return layer, False, []  # made by billing software: its text is exact
        try:
            images = rasterize.pdf_to_images(data, cfg["OCR_MAX_PAGES"])
        except Exception as exc:
            if layer:
                return layer, False, []
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
        raise BadRequestError("Bill reading is not installed on the Main PC.")
    binarize = engine.needs_black_and_white()
    pages = []
    for image in images:
        remaining = int(deadline - time.monotonic())
        if remaining < 5:
            break
        clean = preprocess.prepare(image, is_photo=is_photo, binarize=binarize)
        words = engine.read_words(clean, timeout=remaining)
        pages.append(Page(width=float(clean.shape[1]), height=float(clean.shape[0]), words=words, source="ocr"))
    if not pages:
        if layer:
            return layer, False, []
        raise BadRequestError("Reading the bill took too long. Try a clearer photo or fewer pages.")
    extra = [row.text for page in layer or [] for row in table_parser.group_rows(page.words)]
    return pages, len(pages) < len(images), extra


# ── 2. Pages → draft ─────────────────────────────────────────────────────────

def _draft(pages: list[Page], skipped: bool, store_id: int, supplier_id: int | None,
           extra_lines: list[str] = ()) -> BillExtractOut:
    text_lines = [row.text for page in pages for row in table_parser.group_rows(page.words)]
    header = header_parser.parse(text_lines)
    if extra_lines:  # a scanned PDF's own OCR text: fills what our reading missed in the header
        other = header_parser.parse(list(extra_lines))
        header.gstins += [g for g in other.gstins if g not in header.gstins]
        header.unverified_gstins += [g for g in other.unverified_gstins if g not in header.unverified_gstins]
        header.invoice_number = header.invoice_number or other.invoice_number
        header.invoice_date = header.invoice_date or other.invoice_date
    supplier, supplier_check, bill_gstin = _bill_supplier(header, text_lines + list(extra_lines), store_id,
                                                          supplier_id)
    template = (db.session.scalar(select(SupplierBillTemplate).where(SupplierBillTemplate.supplier_id == supplier.id))
                if supplier else None)

    raw: list[RawLine] = []
    layout_found = None
    used_template = False
    for number, page in enumerate(pages, start=1):
        lines, layout = table_parser.parse_page(page, number, layout_found or (template.columns if template else None))
        raw += lines
        if layout:
            layout_found = layout_found or layout
        elif lines and not layout_found:
            used_template = True
    if supplier and (layout_found or used_template):
        _save_template(supplier.id, layout_found)

    matches = bill_matching_service.match_lines(supplier.id if supplier else None, store_id,
                                                [line.description for line in raw])
    lines_out = [_line_out(line, match) for line, match in zip(raw, matches)]
    bill_rate = None
    if lines_out and all(l.tax_rate is None and "bad_gst" not in l.problems for l in lines_out):
        bill_rate = _bill_gst_rate(header, text_lines)  # no GST column: else each product's own rate is used
        for l in lines_out:
            l.tax_rate = _f(bill_rate)
    lines_total = sum((Decimal(str(l.amount)) for l in lines_out if l.amount is not None), Decimal("0"))

    warnings = []
    if not lines_out:
        warnings.append("no_lines")
    if skipped:
        warnings.append("pages_skipped")
    if used_template:
        warnings.append("used_template")
    if bill_rate is not None:
        warnings.append("gst_from_bill")
    warnings += _total_checks(header, lines_total if lines_out else None)

    return BillExtractOut(
        source=pages[0].source,
        supplier_id=supplier.id if supplier else None,
        supplier_name=supplier.company_name if supplier else None,
        gstin=bill_gstin,
        supplier_check=supplier_check,
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


def _supplier_by_close_gstin(lines: list[str], own: str) -> Supplier | None:
    """OCR misread a character or two of the GSTIN: the one saved supplier whose GSTIN is that close."""
    known = list(db.session.scalars(
        select(Supplier.gstin).where(Supplier.gstin.is_not(None), Supplier.gstin != "", Supplier.is_active.is_(True))))
    gstin = header_parser.closest_gstin(lines, [g for g in known if g.strip().upper() != own], exclude=[own])
    return _supplier_by_gstin([gstin.strip().upper()]) if gstin else None


def _bill_supplier(header: header_parser.BillHeader, lines: list[str], store_id: int,
                   chosen_id: int | None) -> tuple[Supplier | None, str, str | None]:
    """Who sent the bill, from the GSTIN printed on it: (the supplier to use, the check, the supplier's GSTIN).
    The bill's GSTIN wins over the supplier chosen on the screen.

    Only a GSTIN read for sure (its check digit is right) that no supplier has stops the bill ("not_found"). Text
    that merely looks like a GSTIN may be misread: then the person checks the supplier ("unverified")."""
    store = db.session.get(Store, store_id)
    own = (store.gstin or "").strip().upper() if store else ""
    # The store's own GSTIN is printed on the bill too ("Bill to"): it is not the supplier's.
    verified = [g for g in header.gstins if g != own]
    unverified = [g for g in header.unverified_gstins if g != own]
    chosen = db.session.get(Supplier, chosen_id) if chosen_id else None
    found = _supplier_by_gstin(verified + unverified)
    if not found and not verified:
        found = _supplier_by_close_gstin(lines, own)
    if found:
        check = "different" if chosen and chosen.id != found.id else "matched"
        return found, check, found.gstin.upper()
    if verified:
        return None, "not_found", verified[0]  # a GSTIN, but no saved supplier has it
    return chosen, "unverified", None  # no GSTIN could be read for sure: only the person can check


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
    if line.taxable is not None and _printed_taxable_fits(line.taxable, amount, line.gst):
        taxable = line.taxable  # the bill's own Taxable column: after every discount (scheme ₹, cash %)
    elif qty and rate is not None and amount is not None:
        taxable = taxable_value(qty, rate, amount, line.discount, line.gst)
        if taxable is None and "rate_from_amount" not in problems and "qty_from_amount" not in problems:
            problems.append("math_mismatch")
    elif amount is None:
        problems.append("amount_missing")

    total_qty = (qty or Decimal("0")) + (line.free_qty or Decimal("0"))
    unit_price, discount_percent = _rate_and_discount(qty, rate, line.free_qty, line.discount, taxable)
    if discount_percent and (line.scheme or (line.discount is not None and discount_percent != line.discount)):
        problems.append("discounts_combined")  # e.g. scheme ₹331.62 + 1 % cash discount shown as one 17.50 %

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
        discount_percent=float(discount_percent),
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


def _rate_and_discount(qty: Decimal | None, rate: Decimal | None, free_qty: Decimal | None,
                       discount: Decimal | None, taxable: Decimal | None) -> tuple[Decimal | None, Decimal]:
    """(rate, discount %) for the form, so that the server's line sum (purchase_service._calc_line: qty × rate −
    discount %, each rounded to the paisa) gives exactly the bill's taxable value.

    The bill's own rate and %, or its ₹ discount as a %, when that comes out to the paisa. Otherwise (a ₹ discount
    no 2-decimal % gives exactly, or free units) the discount is taken into the rate.
    """
    zero = Decimal("0")
    if not qty or rate is None:
        return None, zero
    rate2 = rate.quantize(_CENT, ROUND_HALF_UP)
    if taxable is None:  # the line's sums don't work: the rate as read, and the line is marked to check
        return rate2, zero
    if free_qty:  # free units come in at the same cost: the bill's value spread over all of them
        return (taxable / (qty + free_qty)).quantize(_CENT, ROUND_HALF_UP), zero
    target = taxable.quantize(_CENT, ROUND_HALF_UP)
    gross = (qty * rate2).quantize(_CENT)
    options: list[Decimal | None] = []
    if discount:
        options += [discount, discount / gross * 100 if gross else None]  # printed as a %; printed in ₹
    if gross:
        options.append((gross - target) / gross * 100)  # all discounts together (scheme ₹ + cash %), or none
    for pct in options:
        if pct is None or not 0 <= pct <= 100:
            continue
        pct = pct.quantize(_CENT, ROUND_HALF_UP)
        line_gross, line_discount, _ = purchase_service._calc_line(qty, rate2, pct, 0)
        if line_gross - line_discount == target:
            return rate2, pct
    return (taxable / qty).quantize(_CENT, ROUND_HALF_UP), zero


def _printed_taxable_fits(taxable: Decimal, amount: Decimal | None, gst: Decimal | None) -> bool:
    """The Taxable column read right: the line's amount is it, or it + GST."""
    if amount is None:
        return True
    tolerance = max(Decimal("1"), abs(amount) * Decimal("0.005"))
    return abs(taxable - amount) <= tolerance or (gst is not None and abs(taxable * (1 + gst / 100) - amount) <= tolerance)


_PERCENT = re.compile(r"(\d{1,2}(?:\.\d{1,2})?)\s*%")
_WHOLE_TAX_ROW = re.compile(r"(?i)\b(igst|gst|tax)\b")  # "GST 5%", "Tax @ 12%": the full rate
_HALF_TAX_ROW = re.compile(r"(?i)\b(cgst|sgst|utgst)\b")  # "CGST 2.5%": half of it


def _bill_gst_rate(header: header_parser.BillHeader, text_lines: list[str]) -> Decimal | None:
    """The one GST rate of a bill that prints no GST % on its item lines, or None when it can't be told for sure.

    1. the printed taxes ÷ the taxable total, when that is a GST rate;
    2. else the one rate printed on the bill's GST / IGST / Tax rows ("GST 5%");
    3. else twice the one rate on its CGST / SGST rows ("CGST 2.5%").
    A bill with two rates (5 % and 12 %) gives None: each line then keeps its product's rate, to check by hand."""
    taxes = sum((t for t in (header.cgst, header.sgst, header.igst) if t is not None), Decimal("0"))
    if header.taxable_total and taxes > 0:
        ratio = taxes / header.taxable_total * 100
        near = [r for r in _GST_RATES if r and abs(r - ratio) <= Decimal("0.1")]
        if near:
            return near[0]
    whole: set[Decimal] = set()
    half: set[Decimal] = set()
    for line in text_lines:
        rates = {d for p in _PERCENT.findall(line) if (d := to_decimal(p)) is not None}
        if _HALF_TAX_ROW.search(line):
            half |= rates
        elif _WHOLE_TAX_ROW.search(line):
            whole |= rates
    whole = {r for r in whole if r in _GST_RATES and r}
    if len(whole) == 1:
        return whole.pop()
    doubled = {r * 2 for r in half if r * 2 in _GST_RATES and r}
    return doubled.pop() if len(doubled) == 1 and not whole else None


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