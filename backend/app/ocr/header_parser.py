"""The bill's header and footer: GSTINs, invoice number, invoice date and the printed totals."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from rapidfuzz.distance import Levenshtein
from rapidfuzz.process import cdist

from app.ocr.normalize import parse_date, to_decimal

_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN_SHAPE = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]")
# What each of the 15 places must be: D digit, L letter, X either, Z the letter Z.
_GSTIN_PLACES = "DDLLLLLDDDDLXZX"
_TO_DIGIT = str.maketrans("OIlSBZQD", "01158200")
_TO_LETTER = str.maketrans("01258", "OIZSB")
# The first two digits are the state: 01-38, 97 (other territory), 99 (centre). "72..." is OCR noise.
_STATE_CODES = {f"{n:02d}" for n in range(1, 39)} | {"97", "99"}
# Characters OCR mixes up, made the same before comparing a bill's text with the saved GSTINs.
_LOOKALIKE = str.maketrans("OQDILSBZG", "000115826")
_MAX_GSTIN_EDITS = 2  # misread / missing / extra characters still accepted when only one saved GSTIN is that close

# One stray word may sit in between: on a scan, the next column's label runs into it ("Invoice Dated No: 8436").
# "Invoice" read with a wrong letter ("Involce") still counts.
_INVOICE_LABEL = re.compile(r"(?i)\b(?:inv[a-z0-9]{1,3}ce|inv|bill)\.?\s*(?:[A-Z]+\s+)?(?:number|no\b|#)\.?")
_INVOICE_VALUE = re.compile(r"(?i)[A-Z0-9][A-Z0-9/\-]{0,29}")
_DATE_LABEL = re.compile(r"(?i)\b(?:invoice\s*date|inv\.?\s*date|bill\s*date|dated|date)\b\s*[:\-]?\s*(.{6,24})")
_AMOUNT = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_TOTALS = (
    ("grand_total", re.compile(r"(?i)\b(grand\s*total|net\s*(amount|amt|payable)|bill\s*amount"
                               r"|inv[a-z0-9]{1,3}ce\s*(total|amount)"  # "Involce Total": one letter misread
                               r"|total\s*amount|amount\s*payable)\b")),
    ("taxable_total", re.compile(r"(?i)\b(taxable\s*(value|amount|amt)|sub\s*-?\s*total)\b")),
    ("cgst", re.compile(r"(?i)\bcgst\b")),
    ("sgst", re.compile(r"(?i)\b(sgst|utgst)\b")),
    ("igst", re.compile(r"(?i)\bigst\b")),
    ("round_off", re.compile(r"(?i)\bround(ed|ing)?\s*-?\s*(off|up|down)\b|\br/o\b")),
)
_MINUS_BRACKET = re.compile(r"\(-\)\s*$")  # "Round Up (-)0.11"
_PLAIN_TOTAL = re.compile(r"(?i)^\W*total\b")


@dataclass
class BillHeader:
    gstins: list[str] = field(default_factory=list)  # every valid GSTIN on the bill: supplier's and the store's
    # Printed exactly like a GSTIN but its check digit is wrong (a misprint, or a sample bill): only used to find
    # a supplier saved with exactly that GSTIN.
    unverified_gstins: list[str] = field(default_factory=list)
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
            if (_GSTIN_SHAPE.fullmatch(gstin) and gstin[:2] in _STATE_CODES and gstin_checksum_ok(gstin)
                    and gstin not in found):
                found.append(gstin)
    return found


def find_unverified_gstins(lines: list[str]) -> list[str]:
    """Exactly GSTIN-shaped text (no OCR fixes) whose check digit is wrong."""
    found: list[str] = []
    for line in lines:
        for m in re.finditer(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", line.upper()):
            if m[0][:2] in _STATE_CODES and not gstin_checksum_ok(m[0]) and m[0] not in found:
                found.append(m[0])
    return found


def _canon(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", text).upper().translate(_LOOKALIKE)


def _windows(texts: list[str], sizes: tuple[int, ...], min_digits: int) -> list[str]:
    out = set()
    for text in texts:
        for size in sizes:
            for i in range(len(text) - size + 1):
                window = text[i:i + size]
                if sum(ch.isdigit() for ch in window) >= min_digits:
                    out.add(window)
    return sorted(out)


def _closest(windows: list[str], pieces: dict[str, set[str]], own_pieces: list[str], max_edits: int) -> list[str]:
    """The saved GSTINs (pieces: piece of text → the GSTINs it belongs to) found at the fewest edits ≤ max_edits.
    Text at least as close to the store's own GSTIN is skipped."""
    if not windows or not pieces:
        return []
    names = list(pieces)
    dist = cdist(windows, names, scorer=Levenshtein.distance, score_cutoff=max_edits + 1)
    near_own = cdist(windows, own_pieces, scorer=Levenshtein.distance).min(axis=1) if own_pieces else None
    best: dict[str, int] = {}
    for w, row in enumerate(dist):
        for p, d in enumerate(row):
            if d > max_edits or (near_own is not None and near_own[w] <= d):
                continue
            for target in pieces[names[p]]:
                best[target] = min(best.get(target, int(d)), int(d))
    if not best:
        return []
    lowest = min(best.values())
    return [t for t, d in best.items() if d == lowest]


def closest_gstin(lines: list[str], known: list[str], exclude: list[str] = ()) -> str | None:
    """The one saved GSTIN printed on the bill although OCR got it partly wrong:
        - the whole GSTIN with up to 2 characters misread, missing or extra, or
        - the bill cut or folded at the edge of the photo: only its last (or first) 10-14 characters show, which
          still hold the supplier's PAN.
    None when nothing is that close, or two saved GSTINs are equally close. Text that is at least as close to an
    excluded GSTIN (the store's own, printed as "Bill to") is not counted."""
    targets: dict[str, set[str]] = {}
    for g in known:
        if g and len(c := _canon(g)) == 15:
            targets.setdefault(c, set()).add(g)
    if not targets:
        return None
    own = [c for g in exclude if g and len(c := _canon(g)) == 15]
    texts = [_canon(line) for line in lines]

    # A GSTIN has 7+ digits, even after a few misreads.
    found = _closest(_windows(texts, (14, 15, 16), 5), {c: {c} for c in targets}, own, _MAX_GSTIN_EDITS)
    if not found:
        for size in range(14, 9, -1):
            pieces: dict[str, set[str]] = {}
            for c in targets:
                pieces.setdefault(c[-size:], set()).add(c)
                pieces.setdefault(c[:size], set()).add(c)
            edits = 1 if size >= 12 else 0  # short pieces must be exact
            sizes = (size - 1, size, size + 1) if edits else (size,)
            own_pieces = [o[-size:] for o in own] + [o[:size] for o in own]
            found = _closest(_windows(texts, sizes, 4), pieces, own_pieces, edits)
            if found:
                break
    if len(found) != 1 or len(targets[found[0]]) != 1:
        return None
    return next(iter(targets[found[0]]))


def _last_amount(line: str) -> Decimal | None:
    amounts = _AMOUNT.findall(line)
    return to_decimal(amounts[-1]) if amounts else None


def _amount_after(line: str, label: re.Match) -> Decimal | None:
    """The last amount between this label and the next total label on the line, so a table header like
    "Taxable  CGST  SGST  Total  Round Up (-)0.11" gives CGST nothing and Round Up −0.11."""
    following = [m.start() for _, p in _TOTALS for m in p.finditer(line) if m.start() >= label.end()]
    segment = line[label.end():min(following, default=len(line))]
    amounts = list(_AMOUNT.finditer(segment))
    if not amounts:
        return None
    value = to_decimal(amounts[-1][0])
    if value is not None and _MINUS_BRACKET.search(segment[:amounts[-1].start()]):
        value = -value
    return value


def _invoice_number(line: str) -> str | None:
    """The first of the 3 words after "Invoice No" that has a digit and is not a date: on a photo the "Dated" box
    next to it can run in between ("Invoice Dated No: :21-Oct-26 8447" → 8447)."""
    m = _INVOICE_LABEL.search(line)
    if not m:
        return None
    for word in line[m.end():].split()[:3]:
        word = word.strip(":.#-/")
        if _INVOICE_VALUE.fullmatch(word) and re.search(r"\d", word) and not parse_date(word):
            return word
    return None


def parse(lines: list[str]) -> BillHeader:
    """lines = the text of every row on every page, top to bottom."""
    header = BillHeader(gstins=find_gstins(lines), unverified_gstins=find_unverified_gstins(lines))

    header.invoice_number = next((n for line in lines if (n := _invoice_number(line))), None)

    for line in lines:
        m = _DATE_LABEL.search(line)
        if m and (d := parse_date(m[1])):
            header.invoice_date = d
            break
    if header.invoice_date is None:  # no "Date:" label: the first date near the top
        header.invoice_date = next((d for line in lines[:15] if (d := parse_date(line))), None)

    # Totals are at the bottom: search upwards, take the last amount after the label.
    for name, pattern in _TOTALS:
        for line in reversed(lines):
            if (m := pattern.search(line)) and (amount := _amount_after(line, m)) is not None:
                setattr(header, name, amount)
                break
    if header.grand_total is None:  # just "Total ...... 1,234.00"
        for line in reversed(lines):
            if _PLAIN_TOTAL.search(line) and (amount := _last_amount(line)) is not None:
                header.grand_total = amount
                break
    return header