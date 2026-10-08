"""Pure functions: line totals, GST, CGST/SGST split, discounts, MRP savings.

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


def item_discount(discount_type: DiscountType, value, line_total, qty, cap=None) -> Decimal:
    """Product/category discount for one line. FIXED is rupees off each unit. A PERCENTAGE offer
    stops at `cap` rupees per line when a cap is set. Never exceeds the line."""
    if discount_type is DiscountType.PERCENTAGE:
        amount = to_decimal(line_total) * to_decimal(value) / Decimal("100")
        if cap is not None:
            amount = min(amount, to_decimal(cap))
    else:
        amount = to_decimal(value) * to_decimal(qty)
    return round_money(min(amount, to_decimal(line_total)))


def bill_discount(discount_type: DiscountType, value, amount, cap=None) -> Decimal:
    """Whole-bill discount on `amount`. FIXED is rupees off the bill. A PERCENTAGE offer stops at
    `cap` rupees when a cap is set. Never exceeds the amount."""
    if discount_type is DiscountType.PERCENTAGE:
        off = to_decimal(amount) * to_decimal(value) / Decimal("100")
        if cap is not None:
            off = min(off, to_decimal(cap))
    else:
        off = to_decimal(value)
    return round_money(min(off, to_decimal(amount)))


def buy_x_get_y_discount(buy_qty: int, get_qty: int, line_total) -> Decimal:
    """'Buy X get Y free' on the same product, shared proportionally across every unit:
    each unit is get / (buy + get) off. So Buy 1 Get 1 with just 1 unit = half price, and a
    full group still works out exactly (Buy 2 Get 1 on 3 units = 1 unit free)."""
    return round_money(to_decimal(line_total) * get_qty / (buy_qty + get_qty))


def qty_price_discount(unit_price, qty, tax_rate, bundle_qty: int, bundle_price, line_total) -> Decimal:
    """'3 for ₹99': each full bundle costs `bundle_price` (incl. GST, as the shelf tag says)
    instead of bundle_qty × unit_price. No discount if the bundle isn't actually cheaper."""
    bundles = int(to_decimal(qty) // bundle_qty)
    bundle_price_ex_gst = to_decimal(bundle_price) * Decimal("100") / (Decimal("100") + to_decimal(tax_rate))
    saving_per_bundle = to_decimal(unit_price) * bundle_qty - bundle_price_ex_gst
    if bundles == 0 or saving_per_bundle <= 0:
        return ZERO
    return round_money(min(saving_per_bundle * bundles, to_decimal(line_total)))


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


def split_gst(tax) -> tuple[Decimal, Decimal]:
    """Intra-state GST is half CGST, half SGST. An odd paisa goes to SGST so the two always add up."""
    tax = round_money(tax)
    cgst = round_money(tax / 2)
    return cgst, tax - cgst


def line_saving(mrp, qty, line_total, discount, tax) -> Decimal:
    """What the customer saved on one line: MRP × qty − what they paid (incl. GST).

    MRP includes GST but our prices don't, so we compare against the amount actually paid.
    Without an MRP, the saving is just the discount on the line.
    """
    if mrp is None:
        return round_money(discount)
    paid = to_decimal(line_total) - to_decimal(discount) + to_decimal(tax)
    return max(round_money(to_decimal(mrp) * to_decimal(qty) - paid), ZERO)


def gst_summary(lines) -> list[dict]:
    """Rate-wise GST table for a receipt/credit note. `lines` need tax_rate, line_total, discount_amount, tax_amount."""
    by_rate: dict[Decimal, list[Decimal]] = {}
    for ln in lines:
        rate = to_decimal(ln.tax_rate)
        taxable_tax = by_rate.setdefault(rate, [ZERO, ZERO])
        taxable_tax[0] += to_decimal(ln.line_total) - to_decimal(ln.discount_amount)
        taxable_tax[1] += to_decimal(ln.tax_amount)
    rows = []
    for rate in sorted(by_rate):
        taxable, tax = by_rate[rate]
        cgst, sgst = split_gst(tax)
        rows.append({"tax_rate": rate, "taxable": round_money(taxable), "cgst": cgst, "sgst": sgst, "tax": round_money(tax)})
    return rows


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
