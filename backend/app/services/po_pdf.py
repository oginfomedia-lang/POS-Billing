"""Purchase order PDF (A4) for the supplier: emailed, shared on WhatsApp or printed.

Built from a PoDocument, which holds only what the supplier may see: internal remarks never reach the PDF.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from fpdf import FPDF
from fpdf.fonts import FontFace

from app.extensions import db
from app.models.enums import PurchaseStatus
from app.models.purchase import PurchaseOrder
from app.models.store import Store
from app.services import pdf_fonts
from app.services.daily_report_service import inr

MARGIN = 12  # mm
STAMPS = {PurchaseStatus.DRAFT: "DRAFT — not yet ordered", PurchaseStatus.CANCELLED: "CANCELLED"}


@dataclass
class PoLine:
    name: str
    sku: str | None
    qty: str  # "12" / "2.5 kg"
    rate: Decimal
    discount_percent: Decimal
    tax_rate: Decimal
    amount: Decimal  # qty × rate, before discount and GST


@dataclass
class PoDocument:
    po_number: str
    stamp: str | None  # DRAFT / CANCELLED, printed under the title
    purchase_date: date
    expected_delivery_date: date | None
    reference_number: str | None
    store_name: str
    store_lines: list[str]  # address, phone, GSTIN
    supplier_name: str
    supplier_lines: list[str]
    ship_to: list[str]
    lines: list[PoLine]
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    shipping: Decimal
    other: Decimal
    grand_total: Decimal
    notes: str | None = None
    totals: list[tuple[str, Decimal]] = field(init=False)

    def __post_init__(self) -> None:
        rows = [("Subtotal", self.subtotal), ("Discount", -self.discount), ("GST", self.tax),
                ("Shipping", self.shipping), ("Other charges", self.other)]
        self.totals = [(label, value) for label, value in rows if value or label == "Subtotal"]


def qty_text(qty, uom: str | None = None) -> str:
    """12.000 -> "12", 2.500 kg -> "2.5 kg" (pieces need no unit)."""
    text = f"{Decimal(str(qty)).normalize():f}"
    return f"{text} {uom}" if uom and uom != "pcs" else text


def order_store(po: PurchaseOrder) -> Store | None:
    """The ordering store; a head-office PO without one uses the first active store."""
    return po.store or db.session.scalar(db.select(Store).where(Store.is_active.is_(True)).order_by(Store.id))


def document(po: PurchaseOrder) -> PoDocument:
    store = order_store(po)
    supplier = po.supplier
    store_lines = [x for x in (
        store.address if store else None,
        f"Ph: {store.phone}" if store and store.phone else None,
        f"GSTIN: {store.gstin}" if store and store.gstin else None,
    ) if x]
    place = ", ".join(x for x in (supplier.city, supplier.state, supplier.pincode) if x)
    supplier_lines = [x for x in (
        f"Attn: {supplier.contact_person}" if supplier.contact_person else None,
        supplier.billing_address,
        place or None,
        f"Ph: {supplier.phone}" if supplier.phone else None,
        supplier.email,
        f"GSTIN: {supplier.gstin}" if supplier.gstin else None,
    ) if x]
    ship_to = [po.shipping_address] if po.shipping_address else (
        [store.name] + ([store.address] if store.address else []) if store else []
    )
    return PoDocument(
        po_number=po.po_number,
        stamp=STAMPS.get(po.status),
        purchase_date=po.purchase_date,
        expected_delivery_date=po.expected_delivery_date,
        reference_number=po.reference_number,
        store_name=store.name if store else "",
        store_lines=store_lines,
        supplier_name=supplier.company_name,
        supplier_lines=supplier_lines,
        ship_to=ship_to,
        lines=[
            PoLine(
                name=i.product_name,
                sku=i.product_sku,
                qty=qty_text(i.ordered_qty, i.product.uom.value if i.product and i.product.uom else None),
                rate=i.unit_price,
                discount_percent=i.discount_percent,
                tax_rate=i.tax_rate,
                amount=i.line_total,
            )
            for i in po.items
        ],
        subtotal=po.subtotal,
        discount=po.discount_amount,
        tax=po.tax_amount,
        shipping=po.shipping_charges,
        other=po.other_charges,
        grand_total=po.grand_total,
        notes=po.notes,
    )


def _pct(value: Decimal) -> str:
    return f"{Decimal(str(value)).normalize():f}"


def _money(value: Decimal) -> str:
    return inr(value, keep_paise=True)


class _PoPdf(FPDF):
    def __init__(self, footer_text: str, total_pages: int | None = None):
        super().__init__(unit="mm", format="A4")
        self.footer_text = footer_text
        # Known from a first pass: fpdf's {nb} placeholder doesn't survive text shaping.
        self.total_pages = total_pages
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(True, margin=MARGIN + 6)
        pdf_fonts.setup(self)
        self.add_page()
        self.font()

    @property
    def inner(self) -> float:
        return self.w - 2 * MARGIN

    def font(self, size: float = 9, bold: bool = False) -> None:
        self.set_font(pdf_fonts.FAMILY, "B" if bold else "", size)

    def text_block(self, x: float, y: float, w: float, title: str, heading: str, lines: list[str]) -> float:
        """A labelled address block at (x, y); returns the y where it ends."""
        self.set_xy(x, y)
        self.font(7.5, bold=True)
        self.set_text_color(110)
        self.cell(w, 4.5, title.upper(), new_x="LEFT", new_y="NEXT")
        self.set_text_color(0)
        self.font(10, bold=True)
        self.multi_cell(w, 5, heading, new_x="LEFT", new_y="NEXT")
        self.font(9)
        for line in lines:
            self.multi_cell(w, 4.5, line, new_x="LEFT", new_y="NEXT")
        return self.get_y()

    def footer(self) -> None:
        self.set_y(-MARGIN - 2)
        self.font(7.5)
        self.set_text_color(120)
        self.cell(self.inner / 2, 4, self.footer_text)
        page = f"Page {self.page_no()}" + (f" of {self.total_pages}" if self.total_pages else "")
        self.cell(self.inner / 2, 4, page, align="R")
        self.set_text_color(0)


def _draw(pdf: _PoPdf, d: PoDocument) -> None:
    # Header: the store on the left, the document title and numbers on the right.
    top = pdf.get_y()
    left_w = pdf.inner * 0.58
    pdf.font(15, bold=True)
    pdf.multi_cell(left_w, 7, d.store_name, new_x="LMARGIN", new_y="NEXT")
    pdf.font(9)
    for line in d.store_lines:
        pdf.multi_cell(left_w, 4.5, line, new_x="LMARGIN", new_y="NEXT")
    left_end = pdf.get_y()

    right_x, right_w = MARGIN + left_w, pdf.inner - left_w
    pdf.set_xy(right_x, top)
    pdf.font(16, bold=True)
    pdf.cell(right_w, 8, "PURCHASE ORDER", align="R", new_x="LEFT", new_y="NEXT")
    if d.stamp:
        pdf.font(9, bold=True)
        pdf.set_text_color(190, 30, 30)
        pdf.cell(right_w, 5, d.stamp, align="R", new_x="LEFT", new_y="NEXT")
        pdf.set_text_color(0)
    meta = [("PO No.", d.po_number), ("Date", d.purchase_date.strftime("%d %b %Y"))]
    if d.expected_delivery_date:
        meta.append(("Deliver by", d.expected_delivery_date.strftime("%d %b %Y")))
    if d.reference_number:
        meta.append(("Reference", d.reference_number))
    for label, value in meta:
        pdf.set_x(right_x)
        pdf.font(9)
        pdf.cell(right_w - 45, 5, label, align="R")
        pdf.font(9, bold=True)
        pdf.cell(45, 5, value, align="R", new_x="LEFT", new_y="NEXT")
    pdf.set_y(max(left_end, pdf.get_y()) + 4)
    pdf.set_draw_color(180)
    pdf.line(MARGIN, pdf.get_y(), pdf.w - MARGIN, pdf.get_y())
    pdf.ln(4)

    # Supplier and delivery address side by side.
    y = pdf.get_y()
    half = (pdf.inner - 8) / 2
    end_a = pdf.text_block(MARGIN, y, half, "Supplier", d.supplier_name, d.supplier_lines)
    end_b = pdf.text_block(MARGIN + half + 8, y, half, "Deliver to", d.ship_to[0] if d.ship_to else "", d.ship_to[1:])
    pdf.set_xy(MARGIN, max(end_a, end_b) + 6)

    # Items.
    pdf.font(8.5)
    heading = FontFace(emphasis="BOLD", fill_color=(235, 235, 235))
    with pdf.table(
        col_widths=(8, 74, 22, 22, 16, 14, 30),
        text_align=("RIGHT", "LEFT", "RIGHT", "RIGHT", "RIGHT", "RIGHT", "RIGHT"),
        headings_style=heading,
        line_height=5,
        padding=1.2,
        borders_layout="HORIZONTAL_LINES",
    ) as table:
        table.row(("#", "Item", "Qty", "Rate", "Disc %", "GST %", "Amount"))
        for n, line in enumerate(d.lines, start=1):
            name = f"{line.name}\nSKU {line.sku}" if line.sku else line.name
            table.row((
                str(n), name, line.qty, _money(line.rate), _pct(line.discount_percent), _pct(line.tax_rate),
                _money(line.amount),
            ))
    pdf.ln(3)

    # Totals, right-aligned under the table.
    label_w, value_w = 40, 34
    x = pdf.w - MARGIN - label_w - value_w
    for label, value in d.totals:
        pdf.set_x(x)
        pdf.font(9)
        pdf.cell(label_w, 5.5, label, align="R")
        pdf.cell(value_w, 5.5, _money(value), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x)
    pdf.font(11, bold=True)
    pdf.cell(label_w, 7, "Grand total", align="R", border="T")
    pdf.cell(value_w, 7, _money(d.grand_total), align="R", border="T", new_x="LMARGIN", new_y="NEXT")

    if d.notes:
        pdf.ln(6)
        pdf.font(9, bold=True)
        pdf.cell(0, 5, "Notes", new_x="LMARGIN", new_y="NEXT")
        pdf.font(9)
        pdf.multi_cell(0, 4.5, d.notes, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(8)
    pdf.font(8.5)
    pdf.set_text_color(90)
    pdf.multi_cell(
        0, 4.5,
        f"Please quote PO No. {d.po_number} on your invoice and delivery challan. "
        "Rates are before GST unless stated; GST as per the rate column.",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_text_color(0)


def render_document(d: PoDocument) -> bytes:
    footer = f"{d.store_name} · {d.po_number}"
    probe = _PoPdf(footer)  # first pass only counts the pages
    _draw(probe, d)
    pdf = _PoPdf(footer, total_pages=probe.page_no())
    _draw(pdf, d)
    pdf.set_title(f"{d.store_name} — Purchase Order {d.po_number}")
    return bytes(pdf.output())


def render(po: PurchaseOrder) -> bytes:
    """The PO as PDF bytes."""
    return render_document(document(po))


def filename(po: PurchaseOrder) -> str:
    return f"{po.po_number}.pdf"
