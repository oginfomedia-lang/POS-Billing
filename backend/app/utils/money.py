"""Decimal helpers (never use float for money)."""
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def round_money(value) -> Decimal:
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def money_add(*values) -> Decimal:
    return round_money(sum(to_decimal(v) for v in values))


def money_mul(a, b) -> Decimal:
    return round_money(to_decimal(a) * to_decimal(b))
