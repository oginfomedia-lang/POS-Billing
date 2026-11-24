"""Direct purchase → "Read from bill": a digital PDF bill (no Tesseract needed) becomes a draft; saving the bill
teaches the app what this supplier calls each product."""
import io
import json
from datetime import date

import pytest
from fpdf import FPDF
from fpdf.enums import TextMode

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.supplier import Supplier
from app.models.supplier_bill_template import SupplierBillTemplate
from app.models.supplier_item_alias import SupplierItemAlias
from tests.factories import make_product

pytestmark = pytest.mark.integration
GSTIN = "27AAPFU0939F1ZV"


@pytest.fixture
def supplier(app):
    s = Supplier(supplier_code="SUP-OCR001", company_name="Shree Traders", gstin=GSTIN,
                 payment_terms=PaymentTerms.NET_30)
    db.session.add(s)
    db.session.commit()
    return s


def _bill_pdf(*lines, number="GT/2311", gstin=GSTIN) -> bytes:
    """A bill as billing software prints it: header, a table, totals."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=10)
    pdf.text(10, 15, f"SHREE TRADERS   GSTIN: {gstin}")
    pdf.text(10, 22, f"Invoice No: {number}    Date: 15/11/2026")
    y = 35
    total = 0.0
    for cells in (("Sr", "Description", "HSN", "Qty", "Rate", "GST%", "Amount"), *lines):
        for x, text in zip((10, 20, 95, 115, 130, 150, 165), cells):
            pdf.text(x, y, text)
        if cells[0] != "Sr":
            total += float(cells[6])
        y += 7
    pdf.text(20, y, "Total")
    pdf.text(165, y, f"{total:.2f}")
    pdf.text(10, y + 10, f"Grand Total {total:.2f}")
    return bytes(pdf.output())


def _extract(client, headers, store, pdf: bytes, **form):
    data = {"file": (io.BytesIO(pdf), "bill.pdf", "application/pdf"), "store_id": str(store.id), **form}
    return client.post("/api/v1/purchases/direct/extract", data=data, headers=headers,
                       content_type="multipart/form-data")


SALT = ("1", "TATA SALT 1KG", "2501", "10", "24.50", "0", "245.00")
OIL = ("2", "FORTUNE SOYABEAN OIL 1L", "1507", "5", "150.00", "5", "787.50")


def test_digital_pdf_becomes_a_draft(client, admin_headers, store, supplier):
    make_product(store, name="Tata Salt 1kg", price="28.00", stock=0)
    resp = _extract(client, admin_headers, store, _bill_pdf(SALT, OIL))
    assert resp.status_code == 200, resp.get_json()
    d = resp.get_json()
    assert d["source"] == "pdf_text"
    assert (d["supplier_id"], d["gstin"]) == (supplier.id, GSTIN)  # found from the GSTIN
    assert (d["invoice_number"], d["invoice_date"], d["grand_total"]) == ("GT/2311", "2026-11-15", 1032.5)
    assert d["warnings"] == []

    salt, oil = d["lines"]
    assert (salt["description"], salt["qty"], salt["unit_price"], salt["hsn_code"]) == ("TATA SALT 1KG", 10, 24.5, "2501")
    assert salt["status"] == "matched" and salt["product"]["name"] == "Tata Salt 1kg"
    assert oil["unit_price"] == 150.0 and oil["tax_rate"] == 5  # 787.50 = 5 × 150 + 5 % GST
    assert oil["status"] == "not_found"  # no such product yet

    db.session.expire_all()
    assert db.session.scalar(db.select(SupplierBillTemplate).filter_by(supplier_id=supplier.id)) is not None


def test_bill_without_gst_column_uses_the_bills_rate_and_skips_the_tax_summary(client, admin_headers, store, supplier):
    """Items with no GST % column, then a "Tax Summary" table: its "GST 5% 180.00 180.00 360.00" row is not an item,
    and every line gets the bill's 5 % (not each product's own rate, e.g. 0 % for loose rice)."""
    make_product(store, name="Rice 5 kg", price="300.00", stock=0, tax_rate="0")
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=10)
    pdf.text(10, 15, f"XYZ TRADERS   GSTIN: {GSTIN}")
    pdf.text(10, 22, "Invoice No: XYZ/0156    Date: 11/09/2026")
    rows = [("Sr", "Product Name", "HSN", "Qty", "Rate", "Amount"),
            ("1", "Toor Dal 1 kg pack", "07132000", "10", "120.00", "1200.00"),
            ("2", "Rice 5 kg", "10063010", "5", "280.00", "1400.00"),
            ("3", "Cooking Oil 1 L", "15119010", "10", "180.00", "1800.00"),
            ("Tax Summary", "Tax Rate", "", "CGST", "SGST", "Total Tax"),
            ("GST", "5%", "", "180.00", "180.00", "360.00")]
    y = 35
    for cells in rows:
        for x, text in zip((10, 30, 95, 120, 140, 165), cells):
            pdf.text(x, y, text)
        y += 7
    pdf.text(120, y + 3, "Sub Total 4400.00")
    pdf.text(120, y + 10, "Grand Total 4620.00")
    resp = _extract(client, admin_headers, store, bytes(pdf.output()))
    assert resp.status_code == 200, resp.get_json()
    d = resp.get_json()
    assert [l["description"] for l in d["lines"]] == ["Toor Dal 1 kg pack", "Rice 5 kg", "Cooking Oil 1 L"]
    assert [l["tax_rate"] for l in d["lines"]] == [5, 5, 5]
    assert "gst_from_bill" in d["warnings"]


def test_saving_the_bill_remembers_the_supplier_name(client, admin_headers, store, supplier):
    oil = make_product(store, name="सोयाबीन तेल फॉर्च्यून 1 लिटर", price="160.00", stock=0)
    first = _extract(client, admin_headers, store, _bill_pdf(OIL)).get_json()
    assert first["lines"][0]["status"] == "not_found"  # the Marathi name doesn't look like the bill's

    body = {"supplier_id": supplier.id, "store_id": store.id, "invoice_number": "GT/2311",
            "invoice_date": str(date.today()), "grand_total": "787.50",
            "items": [{"product_id": oil.id, "qty": "5", "unit_price": "150", "tax_rate": "5",
                       "bill_description": "FORTUNE SOYABEAN OIL 1L"}]}
    saved = client.post("/api/v1/purchases/direct", headers=admin_headers, content_type="multipart/form-data",
                        data={"data": json.dumps(body), "file": (io.BytesIO(b"%PDF-1.4"), "bill.pdf", "application/pdf")})
    assert saved.status_code == 201, saved.get_json()
    assert db.session.scalar(db.select(SupplierItemAlias).filter_by(supplier_id=supplier.id)).product_id == oil.id

    again = _extract(client, admin_headers, store, _bill_pdf(OIL, number="GT/2400")).get_json()
    line = again["lines"][0]
    assert (line["status"], line["match_source"], line["product"]["id"]) == ("matched", "alias", oil.id)


def test_photo_read_by_ocr(client, admin_headers, store, supplier):
    """The OCR path for real: the bill as a tilted phone photo (JPEG). Skipped where no OCR engine is installed."""
    from app.ocr import engine, rasterize

    if not engine.is_available():
        pytest.skip("No OCR engine (RapidOCR / Tesseract) is installed")
    cv2 = pytest.importorskip("cv2")
    import numpy as np
    from PIL import Image

    make_product(store, name="Tata Salt 1kg", price="28.00", stock=0)
    page = np.array(rasterize.pdf_to_images(_bill_pdf(SALT, OIL), 1)[0].convert("L"))
    canvas = np.full((page.shape[0] + 400, page.shape[1] + 400), 50, np.uint8)  # on a dark table
    canvas[200:200 + page.shape[0], 200:200 + page.shape[1]] = page
    turn = cv2.getRotationMatrix2D((canvas.shape[1] / 2, canvas.shape[0] / 2), 3, 1.0)  # tilted 3°
    photo = cv2.warpAffine(canvas, turn, (canvas.shape[1], canvas.shape[0]), borderValue=50)
    jpeg = io.BytesIO()
    Image.fromarray(photo).save(jpeg, format="JPEG", quality=85)

    data = {"file": (io.BytesIO(jpeg.getvalue()), "bill.jpg", "image/jpeg"), "store_id": str(store.id)}
    resp = client.post("/api/v1/purchases/direct/extract", data=data, headers=admin_headers,
                       content_type="multipart/form-data")
    assert resp.status_code == 200, resp.get_json()
    d = resp.get_json()
    assert d["source"] == "ocr"
    assert (d["supplier_id"], d["invoice_number"], d["grand_total"]) == (supplier.id, "GT/2311", 1032.5)
    salt, oil = d["lines"]
    assert (salt["description"], salt["qty"], salt["unit_price"]) == ("TATA SALT 1KG", 10, 24.5)
    assert salt["product"]["name"] == "Tata Salt 1kg"
    assert (oil["qty"], oil["unit_price"], oil["tax_rate"], oil["amount"]) == (5, 150.0, 5, 787.5)


def test_wrong_file_and_missing_store(client, admin_headers, store):
    resp = _extract(client, admin_headers, store, b"hello")
    assert resp.status_code == 400  # not a PDF, not a picture
    resp = client.post("/api/v1/purchases/direct/extract", headers=admin_headers, content_type="multipart/form-data",
                       data={"file": (io.BytesIO(b"%PDF-1.4"), "bill.pdf", "application/pdf")})
    assert resp.status_code == 400  # no store_id


def test_cashier_cannot_read_bills(client, cashier_headers, store):
    assert _extract(client, cashier_headers, store, _bill_pdf(SALT)).status_code == 403

def test_supplier_is_checked_from_the_bill_gstin(client, admin_headers, store, supplier):
    other = Supplier(supplier_code="SUP-OCR002", company_name="Ganesh Agency", payment_terms=PaymentTerms.NET_30)
    db.session.add(other)
    db.session.commit()

    # Nothing chosen: found from the GSTIN.
    d = _extract(client, admin_headers, store, _bill_pdf(SALT)).get_json()
    assert (d["supplier_id"], d["supplier_check"]) == (supplier.id, "matched")

    # The wrong supplier chosen: the bill's GSTIN wins.
    d = _extract(client, admin_headers, store, _bill_pdf(SALT), supplier_id=str(other.id)).get_json()
    assert (d["supplier_id"], d["supplier_check"]) == (supplier.id, "different")

    # Nobody has that GSTIN: not found, and the GSTIN is sent back to add the supplier.
    supplier.gstin = None
    db.session.commit()
    d = _extract(client, admin_headers, store, _bill_pdf(SALT)).get_json()
    assert (d["supplier_id"], d["supplier_check"], d["gstin"]) == (None, "not_found", GSTIN)


def test_misread_gstin_still_finds_the_supplier(client, admin_headers, store, supplier):
    # O for 0, I for 1 and a wrong last character: no exact GSTIN, but only Shree Traders' is that close.
    d = _extract(client, admin_headers, store, _bill_pdf(SALT, gstin="27AAPFUO939FIZW")).get_json()
    assert (d["supplier_id"], d["supplier_check"], d["gstin"]) == (supplier.id, "matched", GSTIN)


def test_gstin_like_noise_never_blocks_the_bill(client, admin_headers, store, supplier):
    # OCR noise shaped like a GSTIN (state 72 doesn't exist): the chosen supplier stays, the person checks it.
    d = _extract(client, admin_headers, store, _bill_pdf(SALT, gstin="72OIBZZ2522Z5Z9"),
                 supplier_id=str(supplier.id)).get_json()
    assert (d["supplier_id"], d["supplier_check"], d["gstin"]) == (supplier.id, "unverified", None)


def test_scanned_pdf_with_bad_ocr_text_is_read_again(client, admin_headers, store, supplier):
    """An "OCR ready" PDF: a scanned page with some program's (wrong) OCR text over it. Our engine reads the
    picture instead."""
    from app.ocr import engine, rasterize

    if not engine.is_available():
        pytest.skip("No OCR engine (RapidOCR / Tesseract) is installed")
    picture = io.BytesIO()
    rasterize.pdf_to_images(_bill_pdf(SALT, OIL), 1)[0].save(picture, format="PNG")
    pdf = FPDF()
    pdf.add_page()
    pdf.image(picture, x=0, y=0, w=pdf.w, h=pdf.h)
    pdf.set_font("helvetica", size=8)
    pdf.text_mode = TextMode.INVISIBLE  # as OCR programs lay their text over the picture
    pdf.text(10, 15, "SHREE TRADER5 GST1N: 72OIBZZ2522Z5Z9 lnvoice N0 GTI23ll Dote l5ll1l2O26 T0TAL")  # bad layer

    resp = _extract(client, admin_headers, store, bytes(pdf.output()))
    assert resp.status_code == 200, resp.get_json()
    d = resp.get_json()
    assert d["source"] == "ocr"
    assert (d["supplier_id"], d["supplier_check"], d["invoice_number"]) == (supplier.id, "matched", "GT/2311")
    assert len(d["lines"]) == 2
