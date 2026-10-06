"""Pure functions: line totals, GST (inclusive/exclusive), CGST/SGST split, discounts, round-off."""
from __future__ import annotations

from decimal import Decimal

from app.utils.money import money_add, money_mul, round_money

ZERO = Decimal("0.00")


def line_amounts(unit_price, qty: int, tax_rate) -> tuple[Decimal, Decimal]:
    """Return (line_total, tax_amount). Prices are tax-exclusive; tax_rate is a percent."""
    line_total = money_mul(unit_price, qty)
    tax_amount = round_money(line_total * Decimal(str(tax_rate)) / Decimal("100"))
    return line_total, tax_amount


def bill_totals(lines: list[tuple[Decimal, Decimal]], discount=ZERO) -> dict[str, Decimal]:
    """lines = [(line_total, tax_amount), ...] -> subtotal / discount / tax / total."""
    subtotal = money_add(ZERO, *(lt for lt, _ in lines))
    tax = money_add(ZERO, *(t for _, t in lines))
    discount = round_money(discount)
    return {
        "subtotal": subtotal,
        "discount_amount": discount,
        "tax_amount": tax,
        "total": round_money(subtotal - discount + tax),
    }
