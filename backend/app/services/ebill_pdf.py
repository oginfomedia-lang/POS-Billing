"""PDF copy of a paid bill (the WhatsApp e-bill). Same data and layout as the printed bill (ReprintPage.tsx).

80 mm wide like the thermal slip; the page is exactly as tall as the bill. Text shaping (uharfbuzz) with a
Devanagari fallback font so Marathi store/product names render correctly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from fpdf import FPDF

from app.schemas.sale_schemas import ReceiptOut
from app.services import pdf_fonts
from app.services.daily_report_service import inr
from app.utils.dates import IST

WIDTH = 80  # mm
MARGIN = 4  # mm
LINE = 4.2  # mm per text line
METHODS = {"cash": "Cash", "card": "Card", "upi": "UPI", "split": "Split"}


def rs(value) -> str:
    return inr(value, keep_paise=True)


_PAISA = Decimal("0.01")


def add_gst(amount, rate) -> Decimal:
    """amount × (1 + GST %), rounded half up to the paisa, as GST is rounded on the bill."""
    amount = Decimal(str(amount or 0))
    return (amount * (1 + Decimal(str(rate or 0)) / 100)).quantize(_PAISA, ROUND_HALF_UP)


@dataclass
class GstLine:
    rate: Decimal  # per unit, incl. GST
    amount: Decimal  # qty × rate before discounts, incl. GST
    offer: Decimal
    manual: Decimal


@dataclass
class ReceiptGst:
    lines: list[GstLine] = field(default_factory=list)
    subtotal: Decimal = Decimal("0")
    item_savings: Decimal = Decimal("0")
    bill_offer: Decimal = Decimal("0")
    reward: Decimal = Decimal("0")


def with_gst(r: ReceiptOut) -> ReceiptGst:
    """Prices are saved before GST; the bill prints every rate, amount and saving with GST so the lines add up to
    the total paid. Same maths as frontend/src/components/pos/receiptGst.ts."""
    out = ReceiptGst()
    for i in r.items:
        bill_offer = max(Decimal("0"), i.discount_amount - i.offer_discount - i.manual_discount - i.reward_discount)
        line = GstLine(add_gst(i.unit_price, i.tax_rate), add_gst(i.line_total, i.tax_rate),
                       add_gst(i.offer_discount, i.tax_rate), add_gst(i.manual_discount, i.tax_rate))
        out.lines.append(line)
        out.subtotal += line.amount
        out.item_savings += line.offer + line.manual
        out.bill_offer += add_gst(bill_offer, i.tax_rate)
        out.reward += add_gst(i.reward_discount, i.tax_rate)
    # Rounding each line can leave the savings a paisa or two off: the biggest saving takes the difference.
    diff = out.subtotal - out.item_savings - out.bill_offer - out.reward - r.total
    if diff:
        if out.item_savings >= out.bill_offer and out.item_savings >= out.reward and out.item_savings > 0:
            out.item_savings += diff
        elif out.bill_offer >= out.reward and out.bill_offer > 0:
            out.bill_offer += diff
        elif out.reward > 0:
            out.reward += diff
    return out


class _Bill(FPDF):
    def __init__(self, height: float):
        super().__init__(unit="mm", format=(WIDTH, height))
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(False)
        pdf_fonts.setup(self)
        self.add_page()
        self.font(8)

    @property
    def inner(self) -> float:
        return WIDTH - 2 * MARGIN

    def font(self, size: float = 8, bold: bool = False) -> None:
        self.set_font("NotoSans", "B" if bold else "", size)

    def center(self, text: str, size: float = 8, bold: bool = False) -> None:
        self.font(size, bold)
        self.multi_cell(self.inner, LINE * size / 8, text, align="C", new_x="LMARGIN", new_y="NEXT")
        self.font()

    def row(self, left: str, right: str, bold: bool = False, size: float = 8, indent: float = 0) -> None:
        """Left text (wraps) with the right text on the first line, right-aligned."""
        self.font(size, bold)
        h = LINE * size / 8
        right_w = self.get_string_width(right) + 1
        y = self.get_y()
        # Right text first: after Devanagari in the left text the fallback font may still be active.
        self.set_xy(WIDTH - MARGIN - right_w, y)
        self.cell(right_w, h, right, align="R")
        self.set_xy(MARGIN + indent, y)
        self.multi_cell(self.inner - indent - right_w, h, left, new_x="LMARGIN", new_y="NEXT")
        self.font()

    def rule(self) -> None:
        self.ln(1)
        self.set_draw_color(150)
        self.set_dash_pattern(dash=0.8, gap=0.6)
        self.line(MARGIN, self.get_y(), WIDTH - MARGIN, self.get_y())
        self.set_dash_pattern()
        self.ln(1.5)


def _draw(pdf: _Bill, r: ReceiptOut) -> None:
    pdf.center(r.store_name, 11, bold=True)
    if r.receipt_header:
        pdf.center(r.receipt_header, bold=True)
    if r.store_phone:
        pdf.center(f"Ph: {r.store_phone}")
    if r.store_gstin:
        pdf.center(f"GSTIN: {r.store_gstin}")
    if r.fssai_number:
        pdf.center(f"FSSAI Lic. No: {r.fssai_number}")
    if r.store_address:
        pdf.center(r.store_address)
    pdf.rule()

    pdf.row("Bill No", r.bill_number)
    pdf.row("Date", r.completed_at.astimezone(IST).strftime("%d %b %Y, %I:%M %p"))
    pdf.row(f"Counter {r.counter_code}" if r.counter_code else "", r.cashier_name)
    if r.customer_mobile:
        pdf.row("Customer", r.customer_mobile)
    pdf.rule()

    gst = with_gst(r)
    pdf.row("Item", "Amt", bold=True)
    for n, (i, g) in enumerate(zip(r.items, gst.lines), start=1):
        pdf.row(f"{n}. {i.product_name}", f"{g.amount}")
        if i.is_variable_weight:
            details = [f"{float(i.qty):.3f} {i.uom} × {g.rate}/{i.uom}"]
        else:
            details = [f"{i.qty} × {g.rate}"]
        if i.hsn_code:
            details.append(f"HSN {i.hsn_code}")
        if i.mrp:
            details.append(f"MRP {i.mrp}")
        pdf.row("  " + " · ".join(details), "", size=7)
        if i.offer_discount > 0:
            pdf.row(f"  {i.offer_name or 'Offer'}", f"-{g.offer}", size=7)
        if i.manual_discount > 0:
            reason = f" ({i.manual_discount_reason})" if i.manual_discount_reason else ""
            pdf.row(f"  Discount{reason}", f"-{g.manual}", size=7)
    pdf.rule()
    items_text, qty_text = item_summary(r)
    pdf.row(items_text, qty_text, bold=True)
    pdf.rule()

    # Everything with GST, so subtotal − savings = total.
    pdf.row("Subtotal", rs(gst.subtotal))
    if gst.item_savings > 0:
        pdf.row("Item savings", f"− {rs(gst.item_savings)}")
    if r.bill_offer_discount > 0:
        pdf.row(r.bill_offer_name or "Bill offer", f"− {rs(gst.bill_offer)}")
    if r.reward_discount > 0:
        pdf.row(f"Reward points ({r.points_redeemed} pts)", f"− {rs(gst.reward)}")
    pdf.ln(0.5)
    pdf.row("Total (incl. GST)", rs(r.total), bold=True, size=11)
    if r.total_saving > 0:
        on_mrp = " on MRP" if any(i.mrp is not None for i in r.items) else ""
        pdf.ln(1)
        pdf.center(f"You saved {rs(r.total_saving)}{on_mrp}!", 9, bold=True)
    if r.points_balance is not None:
        pdf.center(f"Points earned {r.points_earned} · Balance {r.points_balance}")
    pdf.rule()

    for p in r.payments:
        method = p.method.value if hasattr(p.method, "value") else str(p.method)
        pdf.row(f"Paid ({METHODS.get(method, method)})", rs(p.tendered if p.tendered is not None else p.amount))
        if p.change_due is not None:
            pdf.row("Change", rs(p.change_due))
        if p.reference:
            pdf.row("Ref", p.reference)

    if r.receipt_footer:
        pdf.ln(2)
        pdf.center(r.receipt_footer)


def item_summary(r: ReceiptOut) -> tuple[str, str]:
    """The line under the items, same as the printed bill: number of bill lines | total quantity."""
    return f"Total Items: {r.item_lines}", f"Total Qty: {r.total_qty}"


def render(receipt: ReceiptOut) -> bytes:
    """The bill as PDF bytes."""
    # First pass on a very tall page only to measure, second pass on a page that fits exactly.
    probe = _Bill(2000)
    _draw(probe, receipt)
    pdf = _Bill(max(probe.get_y() + MARGIN, 60))
    _draw(pdf, receipt)
    pdf.set_title(f"{receipt.store_name} — Bill {receipt.bill_number}")
    return bytes(pdf.output())

