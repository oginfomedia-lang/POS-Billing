"""The purchase order PDF renders Marathi names and grows onto more pages for long orders."""
import re
from datetime import date
from decimal import Decimal

from app.services import po_pdf


def _doc(lines: int = 3, **overrides) -> po_pdf.PoDocument:
    line = po_pdf.PoLine(
        name="तांदूळ बासमती 25 किलो", sku="KIR-TAN-0001", qty="12", rate=Decimal("1180.50"),
        discount_percent=Decimal("2"), tax_rate=Decimal("5"), amount=Decimal("14166.00"),
    )
    data = dict(
        po_number="PO-20261102-AB12", stamp=None, purchase_date=date(2026, 11, 2),
        expected_delivery_date=date(2026, 11, 5), reference_number=None,
        store_name="श्री गणेश किराणा", store_lines=["Main Road, Pune", "GSTIN: 27ABCDE1234F1Z5"],
        supplier_name="Sharma Traders", supplier_lines=["Market Yard, Pune"], ship_to=["श्री गणेश किराणा"],
        lines=[line] * lines, subtotal=Decimal("100"), discount=Decimal("0"), tax=Decimal("5"),
        shipping=Decimal("0"), other=Decimal("0"), grand_total=Decimal("105"),
    )
    return po_pdf.PoDocument(**{**data, **overrides})


def test_renders_pdf_with_marathi_text():
    pdf = po_pdf.render_document(_doc(notes="सकाळी 10 पूर्वी द्या"))
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000


def _pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))


def test_long_order_spans_pages():
    assert _pages(po_pdf.render_document(_doc(3))) == 1
    assert _pages(po_pdf.render_document(_doc(80, stamp="DRAFT — not yet ordered"))) >= 3


def test_totals_skip_empty_rows():
    labels = [label for label, _ in _doc(discount=Decimal("3"), shipping=Decimal("0")).totals]
    assert labels == ["Subtotal", "Discount", "GST"]


def test_qty_text():
    assert po_pdf.qty_text(Decimal("12.000")) == "12"
    assert po_pdf.qty_text(Decimal("2.500"), "kg") == "2.5 kg"
    assert po_pdf.qty_text(Decimal("3"), "pcs") == "3"
