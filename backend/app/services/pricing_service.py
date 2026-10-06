"""Pure functions: line totals, GST (inclusive/exclusive), CGST/SGST split, discounts, round-off.

Prices are tax-exclusive. Discounts reduce the taxable value, so GST is charged on
(line_total - discount).
"""
from __future__ import annotations

from decimal import Decimal

from app.models.enums import DiscountType
from app.utils.money import money_add, money_mul, round_money, to_decimal

ZERO = Decimal("0.00")


def line_amounts(unit_price, qty: int, tax_rate, discount=ZERO) -> tuple[Decimal, Decimal]:
    """Return (line_total, tax_amount). tax_rate is a percent."""
    line_total = money_mul(unit_price, qty)
    taxable = line_total - round_money(discount)
    tax_amount = round_money(taxable * to_decimal(tax_rate) / Decimal("100"))
    return line_total, tax_amount


def item_discount(discount_type: DiscountType, value, line_total, qty: int) -> Decimal:
    """Product/category discount for one line. FIXED is rupees off each unit. Never exceeds the line."""
    if discount_type is DiscountType.PERCENTAGE:
        amount = to_decimal(line_total) * to_decimal(value) / Decimal("100")
    else:
        amount = to_decimal(value) * qty
    return round_money(min(amount, to_decimal(line_total)))


def bill_discount(discount_type: DiscountType, value, amount) -> Decimal:
    """Whole-bill discount on `amount`. FIXED is rupees off the bill. Never exceeds the amount."""
    if discount_type is DiscountType.PERCENTAGE:
        off = to_decimal(amount) * to_decimal(value) / Decimal("100")
    else:
        off = to_decimal(value)
    return round_money(min(off, to_decimal(amount)))


def allocate(amount, weights: list[Decimal]) -> list[Decimal]:
    """Split `amount` across lines in proportion to `weights`; the rounding remainder goes to the largest line."""
    amount = round_money(amount)
    total = sum(weights, ZERO)
    if amount == 0 or total == 0:
        return [ZERO for _ in weights]
    shares = [round_money(amount * w / total) for w in weights]
    biggest = max(range(len(weights)), key=lambda i: weights[i])
    shares[biggest] += amount - sum(shares, ZERO)
    return shares


def bill_totals(lines: list[tuple[Decimal, Decimal, Decimal]]) -> dict[str, Decimal]:
    """lines = [(line_total, discount_amount, tax_amount), ...] -> subtotal / discount / tax / total."""
    subtotal = money_add(ZERO, *(lt for lt, _, _ in lines))
    discount = money_add(ZERO, *(d for _, d, _ in lines))
    tax = money_add(ZERO, *(t for _, _, t in lines))
    return {
        "subtotal": subtotal,
        "discount_amount": discount,
        "tax_amount": tax,
        "total": round_money(subtotal - discount + tax),
    }
