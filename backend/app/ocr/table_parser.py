"""Words with positions → the bill's item lines.

1. Words whose vertical centres line up form a row.
2. The row with the most column names (Qty, Rate, Amount ...) is the table header; each header word marks
   where its column is. A header printed on two lines ("Billed / Qty", "Sch. / Amt.") is read as one.
   A supplier's last good layout (supplier_bill_templates) is used when no header is found.
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

# Header words (lower case, only letters and %) → our field. A column's words are looked up joined first
# ("Sch." + "Amt." → "schamt", "Taxable" + "Amount" → "taxableamount"), then one by one.
HEADER_WORDS = {
    "taxable": "taxable", "taxableamount": "taxable", "taxableamt": "taxable", "taxablevalue": "taxable",
    "schamt": "scheme", "schamount": "scheme", "schemeamt": "scheme", "schemeamount": "scheme", "schdisc": "scheme",
    "cgst": SKIP, "cgstamt": SKIP, "sgst": SKIP, "sgstamt": SKIP, "igst": SKIP, "igstamt": SKIP, "utgst": SKIP,
    "cess": SKIP, "cessamt": SKIP,
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
# Also the tax summary under the items ("Tax Summary | Tax Rate | CGST ...", "GST 5% 180.00 180.00 360.00"): its
# rows have numbers in the qty/rate/amount columns and were taken as an item.
_END_OF_TABLE = re.compile(r"(?i)^\W*(sub\s*-?\s*total|grand\s*total|total|taxable|amount\s*in\s*words|rupees"
                           r"|(gst|tax|hsn)\s*(wise\s*)?(summary|details|breakup|analysis)|(c|s|i|ut)gst)\b")
# Its title can sit in the Sr. No. column, left of the name column: looked for at the start of the whole row.
_TAX_SUMMARY = re.compile(r"(?i)^\W*((gst|tax|hsn)\s*(wise\s*)?(summary|details|breakup|analysis)|(c|s|i|ut)?gst)\b")


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
    confidence: float  # the lowest OCR confidence of the words the line was read from (not ignored handwriting)
    page: int
    taxable: Decimal | None = None  # the bill's own "Taxable Amount" column, when it has one
    scheme: Decimal | None = None  # a ₹ scheme discount column ("Sch. Amt."), when it has one


def group_rows(words: list[Word]) -> list[Row]:
    """Words → rows, top to bottom; each row's words left to right. "Words" with no letter or digit are dropped:
    on photos they are specks read as "_", ",", "|", and they would glue "Sr" onto "Description" or end up in names."""
    words = [w for w in words if re.search(r"[A-Za-z0-9]", w.text)]
    if not words:
        return []
    heights = sorted(w.height for w in words)
    line_height = heights[len(heights) // 2] or 1
    # A tilted photo: each printed line runs slightly up or down across the page, and across a wide table its
    # right end reaches the next line's height. Rows are grouped along the text's own slope instead.
    slope = text_slope(words, line_height)
    level = lambda w: w.yc - slope * w.xc  # noqa: E731 - the height the word's line has at the left edge
    rows: list[Row] = []
    levels: list[list[float]] = []
    for w in sorted(words, key=level):
        if rows and abs(level(w) - sum(levels[-1]) / len(levels[-1])) <= 0.6 * line_height:
            rows[-1].words.append(w)
            levels[-1].append(level(w))
        else:
            rows.append(Row([w]))
            levels.append([level(w)])
    for row in rows:
        row.words.sort(key=lambda w: w.x0)
    return rows


def text_slope(words: list[Word], line_height: float) -> float:
    """How far the text lines go down per pixel to the right (0 for a straight scan). Measured between each word
    and the next word to its right on the same line; the median ignores pairs that jump to another line."""
    by_x = sorted(words, key=lambda w: w.x0)
    slopes = []
    for i, w in enumerate(by_x):
        best = None
        for other in by_x[i + 1:]:
            gap = other.x0 - w.x1
            if gap > 6 * line_height:
                break
            if gap < -0.5 * line_height or abs(other.yc - w.yc) > 0.8 * line_height:
                continue
            if best is None or abs(other.yc - w.yc) < abs(best.yc - w.yc):
                best = other
        if best is not None and best.xc - w.xc > line_height:
            slopes.append((best.yc - w.yc) / (best.xc - w.xc))
    if len(slopes) < 10:
        return 0.0
    slopes.sort()
    median = slopes[len(slopes) // 2]
    return median if abs(median) <= 0.1 else 0.0  # more than ~6°: not a tilt, leave it


def _header_field(text: str) -> str | None:
    return HEADER_WORDS.get(re.sub(r"[^a-z%]", "", text.lower()))


def _header_cells(row: Row, second_line: Row | None = None) -> list[list]:
    """Header words → cells [field, x0, x1]. Words close together are one cell ("Batch No", "Item Name"),
    unless they name two different columns ("Qty Rate" printed tight). Words of a second header line join the
    cell they sit under ("Billed" over "Qty")."""
    gap_limit = max(w.height for w in row.words)  # about one letter height: a space, not a column gap
    below = second_line.words if second_line else []

    def overlap(a: Word, b: Word) -> float:
        return min(a.x1, b.x1) - max(a.x0, b.x0)

    def meaning(w: Word) -> str | None:
        # A word with no meaning of its own takes the one printed under it: "Billed" over "Qty" is the Qty column,
        # so it is glued neither onto "MRP" before it nor "Rate" after it just because they are printed close.
        return _header_field(w.text) or next(
            (g for s in below if overlap(s, w) > 0 and (g := _header_field(s.text)) not in (None, SKIP)), None)

    # Text from beside the table on the header's line (a "Contact Details:" box) lies right on top of real column
    # names on a tilted photo: a word that means nothing and overlaps one that does is not part of the header.
    words = [w for w in row.words
             if meaning(w) or not any(o is not w and meaning(o) and overlap(o, w) > 0.3 * min(o.x1 - o.x0, w.x1 - w.x0)
                                      for o in row.words)]
    cells: list[list] = []  # [field of its first-line words, x0, x1, words]
    for w in words:
        own = meaning(w)
        if cells and w.x0 - cells[-1][2] < gap_limit and (cells[-1][0] is None or own is None or cells[-1][0] == own):
            cells[-1][0] = cells[-1][0] or own
            cells[-1][2] = w.x1
            cells[-1][3].append(w)
        else:
            cells.append([own, w.x0, w.x1, [w]])
    for w in second_line.words if second_line else []:
        under = max(cells, key=lambda c: (min(c[2], w.x1) - max(c[1], w.x0), -abs((c[1] + c[2]) / 2 - w.xc)))
        under[3].append(w)
    for cell in cells:
        joined = HEADER_WORDS.get("".join(re.sub(r"[^a-z%]", "", w.text.lower()) for w in cell[3]))
        cell[0] = joined or next((f for w in cell[3] if (f := _header_field(w.text))), None)
        del cell[3]
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
        fields = {f for w in row.words if (f := _header_field(w.text))} - {SKIP}
        if len(fields) >= 3 and ({"qty", "amount"} & fields) and (best is None or len(fields) > best[0]):
            best = (len(fields), i)
    if best is None:
        return None
    index = best[1]
    header = rows[index]
    letter = max(w.height for w in header.words)
    # A second header line: right below, and no digits in it (an item row always has some).
    below = rows[index + 1] if index + 1 < len(rows) else None
    if below and (below.yc - header.yc > 2 * letter or any(re.search(r"\d", w.text) for w in below.words)):
        below = None
    cells = _header_cells(header, below)
    if below:
        index += 1  # the items start after the second line
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
    return index, columns


def _row_cells(row: Row, columns: list[Column]) -> dict[str, list[Word]]:
    out: dict[str, list[Word]] = defaultdict(list)
    for w in row.words:
        col = next((c for c in columns if c.x0 <= w.xc < c.x1), None)
        if col and col.field != SKIP:
            out[col.field].append(w)
    return out


_AMOUNT_WORD = re.compile(r"\d[\d,]*[.,]\d{2}")


_GLUED_AFTER_PAISE = re.compile(r"(\d[\d,]*[.,]\d{2})\d{1,4}")


def _money(text: str | None, paise: bool = False):
    """A money cell. Shop staff write on bills (shelf codes, ticks, sale prices) next to the printed numbers:
    "239.78 S99" is 239.78 when it holds exactly one printed amount (digits with paise).
    paise=True (Total, Taxable, Scheme columns: always printed with exactly 2 decimals): "2,000.00250" is 2,000.00
    with a handwritten 250 written right after it."""
    if paise and text and (glued := _GLUED_AFTER_PAISE.fullmatch(text.strip())):
        text = glued[1]
    value = to_decimal(text)
    if value is not None or not text:
        return value
    printed = [p for p in text.split() if _AMOUNT_WORD.fullmatch(p)]
    return to_decimal(printed[0]) if len(printed) == 1 else None


_PRICE_IN_NAME = re.compile(r"(?i)\bRs?\.?\s?(\d{1,5})(?![\d.]*\s?(?:ml|l|ltr|g|gm|kg|pcs)\b)")


def _mrp(text: str | None, name: str) -> Decimal | None:
    """The printed MRP. Staff write their own selling price over or next to it ("9 10", "330", "N025"). Suppliers
    often print the MRP in the name too ("Pen Blue R10", "Aerosol Rs99"): the number that agrees with it wins; with
    no such name, a cell with more than one number is not trusted."""
    numbers = re.findall(r"\d+(?:\.\d+)?", (text or "").translate(str.maketrans("OoSs", "0055")))
    named = _PRICE_IN_NAME.findall(name)
    if named:
        # Printed by the supplier, so it beats whatever is in the cell ("330" with "Rs30": a handwritten 3 in front).
        return Decimal(named[-1].lstrip("0") or "0")
    return Decimal(numbers[0]) if len(numbers) == 1 else None


def _confidence(cells: dict[str, list[Word]], text: dict[str, str], name: str) -> float:
    """How sure OCR was of the words this line was actually read from. Handwriting the line ignored (beside a
    printed amount, over a printed MRP) doesn't count: it would mark a well-read line "hard to read"."""
    confs: list[float] = []
    for field_name, words in cells.items():
        if field_name in ("rate", "amount", "taxable", "scheme") and to_decimal(text.get(field_name)) is None:
            words = [w for w in words if _AMOUNT_WORD.fullmatch(w.text)]  # only the printed amount was used
        elif field_name == "mrp" and _PRICE_IN_NAME.search(name):
            continue  # the MRP came from the name
        confs += [w.conf for w in words]
    return min(confs, default=100.0)


def _fits(qty: Decimal, rate: Decimal, amount: Decimal | None, taxable: Decimal | None,
          discount: Decimal | None, gst: Decimal | None, scheme: Decimal | None) -> bool:
    """qty × rate agrees with the line's printed amounts (after its discount, with or without GST)."""
    if amount is not None and taxable_value(qty, rate, amount, discount, gst) is not None:
        return True
    if taxable is None:
        return False
    gross = qty * rate
    tolerance = max(Decimal("1"), taxable * Decimal("0.005"))
    after = [gross, gross - (scheme or 0)]
    if discount:
        after += [gross * (1 - discount / 100), (gross - (scheme or 0)) * (1 - discount / 100)]
    return any(abs(v - taxable) <= tolerance for v in after)


def _split_qty_from_rate(rate_text: str | None, **sums) -> tuple[Decimal, Decimal] | None:
    """ "1249.70" in the rate column and nothing under Qty: OCR joined qty 1 and rate 249.70 into one word. The
    split whose qty × rate agrees with the line's amounts, if exactly one does."""
    digits = (rate_text or "").replace(",", "")
    if not re.fullmatch(r"\d{2,}\.\d{2}", digits):
        return None
    whole = digits.split(".")[0]
    fits = []
    for k in range(1, min(4, len(whole))):
        qty, rate = Decimal(whole[:k]), Decimal(digits[k:])
        if qty > 0 and rate > 0 and _fits(qty, rate, **sums):
            fits.append((qty, rate))
    return fits[0] if len(fits) == 1 else None


def _split_merged(text: dict[str, str], field: str, into: str) -> None:
    """ "120.00 600.00" in the rate column: the amount slid into it (the column edge fell between the two).
    The first number is this column's; the last goes to the next column when that one is empty."""
    parts = (text.get(field) or "").split()
    if len(parts) < 2 or not all(_AMOUNT_WORD.search(p) for p in (parts[0], parts[-1])):
        return
    text[field] = parts[0]
    if not text.get(into):
        text[into] = parts[-1]


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
        _split_merged(text, "rate", "amount")
        name = text.get("name", "")
        qty, free = parse_qty(text.get("qty"))
        rate, amount = _money(text.get("rate")), _money(text.get("amount"), paise=True)
        numbers = sum(v is not None for v in (qty, rate, amount))

        if (_END_OF_TABLE.match(name) or (not name and _END_OF_TABLE.search(row.text))
                or _TAX_SUMMARY.match(row.text)):
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
        taxable, scheme = _money(text.get("taxable"), paise=True), _money(text.get("scheme"), paise=True)
        # Qty and rate read as one word ("1249.70"): it sits under one of the two columns and the other is empty.
        if any(c.field == "qty" for c in columns) and bool(text.get("qty")) != bool(text.get("rate")):
            split = _split_qty_from_rate(text.get("qty") or text.get("rate"), amount=amount, taxable=taxable,
                                         discount=discount, gst=gst, scheme=scheme)
            if split:
                qty, rate = split
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
            mrp=_mrp(text.get("mrp"), name),
            discount=discount,
            gst=gst,
            batch=text.get("batch") or None,
            expiry=parse_expiry(text.get("expiry")),
            amount=amount,
            confidence=_confidence(cells, text, name),
            page=page_no,
            taxable=taxable,
            scheme=scheme,
        ))
    return lines, layout