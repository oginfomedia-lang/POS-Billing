"""Indian mobile numbers: clean up what the cashier typed, and mask it for printed receipts."""
from __future__ import annotations

import re

from app.errors.exceptions import AppError

_MOBILE = re.compile(r"[6-9]\d{9}")


def normalize_mobile(raw: str | None) -> str | None:
    """'+91 98765-43210' -> '9876543210'. Empty -> None. Anything else that isn't a valid mobile -> 400."""
    if raw is None:
        return None
    digits = re.sub(r"[\s\-()]", "", str(raw))
    if not digits:
        return None
    if digits.startswith("+91"):
        digits = digits[3:]
    elif len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not _MOBILE.fullmatch(digits):
        raise AppError("Enter a valid 10-digit mobile number.")
    return digits


def is_mobile(text: str | None) -> bool:
    try:
        return normalize_mobile(text) is not None
    except AppError:
        return False


def mask_mobile(mobile: str | None) -> str | None:
    """'9876543210' -> '98XXXXX210' (for slips the customer may throw away)."""
    if not mobile:
        return None
    return f"{mobile[:2]}{'X' * (len(mobile) - 5)}{mobile[-3:]}"
