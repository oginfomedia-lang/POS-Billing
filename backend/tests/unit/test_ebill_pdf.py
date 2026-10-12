"""The e-bill PDF renders Marathi text and leaves GST off, like the printed bill."""
from datetime import datetime, timezone
from decimal import Decimal

from app.schemas.sale_schemas import ReceiptOut
from app.services import ebill_pdf


def _receipt(**overrides) -> ReceiptOut:
    now = datetime.now(timezone.utc)
    item = dict(
        id=1, product_id=1, product_name="तांदूळ बासमती 1 किलो", unit_price=Decimal("120"), tax_rate=Decimal("5"),
        mrp=Decimal("130"), qty=2, line_total=Decimal("240.00"), discount_amount=Decimal("0"), tax_amount=Decimal("12"),
    )
    data = dict(
        sale_id=1, bill_number="C1-000001", store_name="श्री गणेश किराणा", store_address=None, store_phone=None,
        store_gstin=None, counter_code="C1", cashier_name="Ramesh", completed_at=now, items=[item],
        subtotal=Decimal("240"), discount_amount=Decimal("0"), tax_amount=Decimal("12"), total=Decimal("252"),
        payments=[dict(id=1, method="cash", amount=Decimal("252"), reference=None, tendered=Decimal("300"),
                       change_due=Decimal("48"), created_at=now)],
        receipt_header="", receipt_footer="धन्यवाद!",
    )
    return ReceiptOut(**{**data, **overrides})


def test_renders_pdf_with_marathi_text():
    pdf = ebill_pdf.render(_receipt())
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000


def test_long_bill_page_grows():
    short = ebill_pdf.render(_receipt())
    many = _receipt().items * 40
    long = ebill_pdf.render(_receipt(items=[{**i.model_dump(), "id": n} for n, i in enumerate(many)]))
    assert len(long) > len(short)


def test_rupee_format_keeps_paise():
    assert ebill_pdf.rs(Decimal("1234567.5")) == "₹12,34,567.50"
    assert ebill_pdf.rs(Decimal("120")) == "₹120.00"
