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
# An amount with paise, a space, then another number: two cells read as one (the column edge fell between them).
_TWO_AMOUNTS = re.compile(r"\d[.,]\d{2}\s+\S*\d")
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}


def to_decimal(text: str | None) -> Decimal | None:
    """ "1,24,500.00" → 124500.00, "24.50/-" → 24.50, "1O" → 10, "₹ 99" → 99, "10 PCS" → 10; words → None."""
    if text is None:
        return None
    s = _CURRENCY.sub("", str(text).strip())
    if _TWO_AMOUNTS.search(s):
        return None  # "120.00 600.00": two amounts in one cell, not 12000600.00
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