"""PDF copy of a paid bill (the WhatsApp e-bill). Same data and layout as the printed bill (ReprintPage.tsx).

80 mm wide like the thermal slip; the page is exactly as tall as the bill. Text shaping (uharfbuzz) with a
Devanagari fallback font so Marathi store/product names render correctly.
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from app.schemas.sale_schemas import ReceiptOut
from app.services.daily_report_service import inr
from app.utils.dates import IST

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
WIDTH = 80  # mm
MARGIN = 4  # mm
LINE = 4.2  # mm per text line
METHODS = {"cash": "Cash", "card": "Card", "upi": "UPI", "split": "Split"}


def rs(value) -> str:
    return inr(value, keep_paise=True)


class _Bill(FPDF):
    def __init__(self, height: float):
        super().__init__(unit="mm", format=(WIDTH, height))
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(False)
        for family, file in (("NotoSans", "NotoSans"), ("NotoDeva", "NotoSansDevanagari")):
            self.add_font(family, "", str(FONTS / f"{file}-Regular.ttf"))
            self.add_font(family, "B", str(FONTS / f"{file}-Bold.ttf"))
        self.set_fallback_fonts(["NotoDeva"])
        self.set_text_shaping(True)
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
    if r.store_address:
        pdf.center(r.store_address)
    if r.store_phone:
        pdf.center(f"Ph: {r.store_phone}")
    if r.store_gstin:
        pdf.center(f"GSTIN: {r.store_gstin}")
    if r.receipt_header:
        pdf.center(r.receipt_header)
    pdf.rule()

    pdf.row("Bill No", r.bill_number)
    pdf.row("Date", r.completed_at.astimezone(IST).strftime("%d %b %Y, %I:%M %p"))
    pdf.row(f"Counter {r.counter_code}" if r.counter_code else "", r.cashier_name)
    if r.customer_mobile:
        pdf.row("Customer", r.customer_mobile)
    pdf.rule()

    pdf.row("Item", "Amt", bold=True)
    for i in r.items:
        pdf.row(i.product_name, f"{i.line_total}")
        details = [f"{i.qty} × {i.unit_price}"]
        if i.hsn_code:
            details.append(f"HSN {i.hsn_code}")
        if i.mrp:
            details.append(f"MRP {i.mrp}")
        pdf.row("  " + " · ".join(details), "", size=7)
        if i.offer_discount > 0:
            pdf.row(f"  {i.offer_name or 'Offer'}", f"-{i.offer_discount}", size=7)
        if i.manual_discount > 0:
            reason = f" ({i.manual_discount_reason})" if i.manual_discount_reason else ""
            pdf.row(f"  Discount{reason}", f"-{i.manual_discount}", size=7)
    pdf.rule()

    item_savings = r.discount_amount - r.bill_offer_discount - r.reward_discount
    pdf.row("Subtotal", rs(r.subtotal))
    if item_savings > 0:
        pdf.row("Item savings", f"− {rs(item_savings)}")
    if r.bill_offer_discount > 0:
        pdf.row(r.bill_offer_name or "Bill offer", f"− {rs(r.bill_offer_discount)}")
    if r.reward_discount > 0:
        pdf.row(f"Reward points ({r.points_redeemed} pts)", f"− {rs(r.reward_discount)}")
    pdf.ln(0.5)
    pdf.row("TOTAL", rs(r.total), bold=True, size=11)
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


def render(receipt: ReceiptOut) -> bytes:
    """The bill as PDF bytes."""
    # First pass on a very tall page only to measure, second pass on a page that fits exactly.
    probe = _Bill(2000)
    _draw(probe, receipt)
    pdf = _Bill(max(probe.get_y() + MARGIN, 60))
    _draw(pdf, receipt)
    pdf.set_title(f"{receipt.store_name} — Bill {receipt.bill_number}")
    return bytes(pdf.output())

