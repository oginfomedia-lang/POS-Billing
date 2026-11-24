"""Goods arrived without a PO: one bill makes PO + goods receipt + invoice together, or nothing at all."""
import io
import json
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.purchase import GoodsReceipt, PurchaseOrder
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from tests.factories import make_product

pytestmark = pytest.mark.integration
TODAY = str(date.today())


@pytest.fixture
def supplier(app):
    s = Supplier(supplier_code="SUP-DIR001", company_name="Priya Traders", payment_terms=PaymentTerms.NET_30)
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture
def godown_on(client, admin_headers):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    client.put("/api/v1/settings", json={**s, "godown_enabled": True}, headers=admin_headers)


def _post(client, headers, body, with_file=True):
    form = {"data": json.dumps(body)}
    if with_file:
        form["file"] = (io.BytesIO(b"%PDF-1.4"), "bill.pdf", "application/pdf")
    return client.post("/api/v1/purchases/direct", data=form, headers=headers, content_type="multipart/form-data")


def _bill(supplier, store, *lines, number="INV-889", total=None, **extra):
    goods = sum(Decimal(l["qty"]) * Decimal(l["unit_price"]) * (1 + Decimal(l.get("tax_rate", "0")) / 100)
                for l in lines)
    return {"supplier_id": supplier.id, "store_id": store.id, "invoice_number": number, "invoice_date": TODAY,
            "grand_total": str(total if total is not None else goods.quantize(Decimal("0.01"))),
            "items": list(lines), **extra}


def _counts():
    db.session.expire_all()
    return tuple(db.session.scalar(db.select(db.func.count()).select_from(m))
                 for m in (PurchaseOrder, GoodsReceipt, SupplierInvoice))


def test_one_bill_makes_po_receipt_and_invoice(client, admin_headers, store, supplier, godown_on):
    sugar = make_product(store, name="Sugar", price="45.00", stock=0)
    milk = make_product(store, name="Milk", price="30.00", stock=0)
    resp = _post(client, admin_headers, _bill(
        supplier, store,
        {"product_id": sugar.id, "qty": "20", "unit_price": "42", "tax_rate": "5"},  # godown (default)
        {"product_id": milk.id, "qty": "10", "unit_price": "25", "to_shop": True},  # straight to the shelf
    ))
    assert resp.status_code == 201, resp.get_json()
    po = resp.get_json()["purchase_order"]
    assert po["is_direct"] and po["status"] == "received" and po["email_status"] is None  # never emailed
    assert resp.get_json()["invoice"]["verification_status"] == "verified"

    db.session.expire_all()
    s = db.session.scalar(db.select(Inventory).filter_by(store_id=store.id, product_id=sugar.id))
    m = db.session.scalar(db.select(Inventory).filter_by(store_id=store.id, product_id=milk.id))
    assert (s.qty_on_hand, s.godown_qty) == (Decimal("20"), Decimal("20"))  # in the godown
    assert (m.qty_on_hand, m.godown_qty) == (Decimal("10"), Decimal("0"))  # on the shelf
    assert db.session.get(Product, sugar.id).cost_price == Decimal("42.0000")


def test_new_product_gets_gst_hsn_mrp_from_the_bill(client, admin_headers, store, supplier):
    pid = client.post("/api/v1/products/pending", json={"name": "Parle Marie 250g", "supplier_id": supplier.id},
                      headers=admin_headers).get_json()["id"]
    resp = _post(client, admin_headers, _bill(supplier, store, {
        "product_id": pid, "qty": "10", "unit_price": "18", "tax_rate": "18", "mrp": "25", "hsn_code": "1905"}))
    assert resp.status_code == 201, resp.get_json()
    p = db.session.get(Product, pid)
    assert (p.tax_rate, p.mrp, p.hsn_code, p.details_pending) == (Decimal("18.00"), Decimal("25.00"), "1905", True)


def test_duplicate_invoice_number_saves_nothing(client, admin_headers, store, supplier):
    """The unit of work: the invoice step fails, so the PO and the stock are undone too."""
    oil = make_product(store, name="Oil", price="150.00", stock=0)
    line = {"product_id": oil.id, "qty": "5", "unit_price": "120"}
    assert _post(client, admin_headers, _bill(supplier, store, line)).status_code == 201
    before = _counts()

    again = _post(client, admin_headers, _bill(supplier, store, line))  # same INV-889
    assert again.status_code == 409
    assert _counts() == before  # no second PO, receipt or invoice
    db.session.expire_all()
    stock = db.session.scalar(db.select(Inventory).filter_by(store_id=store.id, product_id=oil.id))
    assert stock.qty_on_hand == Decimal("5")  # not 10


def test_bill_file_is_required(client, admin_headers, store, supplier):
    oil = make_product(store, name="Oil", price="150.00", stock=0)
    resp = _post(client, admin_headers, _bill(supplier, store, {"product_id": oil.id, "qty": "5", "unit_price": "120"}),
                 with_file=False)
    assert resp.status_code == 400 and _counts() == (0, 0, 0)


def test_total_difference_needs_a_reason(client, admin_headers, store, supplier):
    oil = make_product(store, name="Oil", price="150.00", stock=0)
    line = {"product_id": oil.id, "qty": "5", "unit_price": "120"}
    assert _post(client, admin_headers, _bill(supplier, store, line, total="700")).status_code == 400
    assert _counts() == (0, 0, 0)
    ok = _post(client, admin_headers, _bill(supplier, store, line, total="700", difference_reason="Freight added"))
    assert ok.status_code == 201 and ok.get_json()["invoice"]["verification_status"] == "disputed"


def test_same_product_twice_is_refused(client, admin_headers, store, supplier):
    oil = make_product(store, name="Oil", price="150.00", stock=0)
    line = {"product_id": oil.id, "qty": "5", "unit_price": "120"}
    assert _post(client, admin_headers, _bill(supplier, store, line, line)).status_code == 422


def test_cashier_cannot(client, cashier_headers, store, supplier):
    oil = make_product(store, name="Oil", price="150.00", stock=0)
    resp = _post(client, cashier_headers, _bill(supplier, store, {"product_id": oil.id, "qty": "1", "unit_price": "1"}))
    assert resp.status_code == 403


def test_discount_on_the_bill(client, admin_headers, store, supplier):
    """Taxable = qty × rate − discount %, total = taxable + GST: the bill's total matches to the paisa, the
    invoice needs no reason, and stock is costed after the discount (before GST)."""
    sugar = make_product(store, name="Sugar", price="45.00", stock=0)
    # 10 × 100 = 1000.00, 2 % off = 980.00, 5 % GST = 49.00 → 1029.00
    resp = _post(client, admin_headers, _bill(
        supplier, store,
        {"product_id": sugar.id, "qty": "10", "unit_price": "100", "discount_percent": "2", "tax_rate": "5"},
        total="1029.00",
    ))
    assert resp.status_code == 201, resp.get_json()
    po = resp.get_json()["purchase_order"]
    assert (Decimal(po["subtotal"]), Decimal(po["discount_amount"]), Decimal(po["tax_amount"]), Decimal(po["grand_total"])) \
        == (Decimal("1000.00"), Decimal("20.00"), Decimal("49.00"), Decimal("1029.00"))
    invoice = resp.get_json()["invoice"]
    assert invoice["verification_status"] == "verified" and Decimal(invoice["difference"]) == 0

    db.session.expire_all()
    assert db.session.get(Product, sugar.id).cost_price == Decimal("98.0000")  # 100 − 2 %, before GST


# ── Several photos of one bill ────────────────────────────────────────────────

def _photo(color) -> io.BytesIO:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), color).save(buf, "PNG")
    buf.seek(0)
    return buf


def test_several_photos_are_saved_as_one_pdf(client, admin_headers, store, supplier):
    from app.models.supplier_document import SupplierDocument
    oil = make_product(store, name="Oil", price="150.00", stock=0)
    form = {"data": json.dumps(_bill(supplier, store, {"product_id": oil.id, "qty": "5", "unit_price": "120"})),
            "file": [(_photo("white"), "top.png", "image/png"), (_photo("gray"), "bottom.png", "image/png")]}
    resp = client.post("/api/v1/purchases/direct", data=form, headers=admin_headers, content_type="multipart/form-data")
    assert resp.status_code == 201, resp.get_json()
    docs = list(db.session.scalars(db.select(SupplierDocument)))
    assert len(docs) == 1 and docs[0].mime_type == "application/pdf"


def test_a_pdf_and_a_photo_together_are_refused(client, admin_headers, store, supplier):
    oil = make_product(store, name="Oil", price="150.00", stock=0)
    form = {"data": json.dumps(_bill(supplier, store, {"product_id": oil.id, "qty": "5", "unit_price": "120"})),
            "file": [(io.BytesIO(b"%PDF-1.4"), "bill.pdf", "application/pdf"), (_photo("white"), "p.png", "image/png")]}
    resp = client.post("/api/v1/purchases/direct", data=form, headers=admin_headers, content_type="multipart/form-data")
    assert resp.status_code == 400 and _counts() == (0, 0, 0)


# ── Correcting a saved direct purchase ───────────────────────────────────────

def _put(client, headers, po_id, body):
    return client.put(f"/api/v1/purchases/{po_id}/direct", data={"data": json.dumps(body)}, headers=headers,
                      content_type="multipart/form-data")


def test_correcting_a_saved_bill(client, admin_headers, store, supplier):
    sugar = make_product(store, name="Sugar", price="45.00", stock=0)
    po_id = _post(client, admin_headers, _bill(
        supplier, store, {"product_id": sugar.id, "qty": "20", "unit_price": "42", "batch_number": "B1"})
    ).get_json()["purchase_order"]["id"]

    draft = client.get(f"/api/v1/purchases/{po_id}/direct", headers=admin_headers).get_json()
    assert draft["invoice_number"] == "INV-889" and draft["bill_file_name"] == "bill.pdf"
    assert draft["items"][0]["qty"] == 20 and draft["items"][0]["batch_number"] == "B1"
    assert draft["items"][0]["product"]["id"] == sugar.id

    # The bill really said 15 at ₹40; no new file = the saved bill is kept.
    resp = _put(client, admin_headers, po_id, _bill(
        supplier, store, {"product_id": sugar.id, "qty": "15", "unit_price": "40"}))
    assert resp.status_code == 200, resp.get_json()
    new_po = resp.get_json()["purchase_order"]
    assert new_po["id"] != po_id and new_po["status"] == "received"

    db.session.expire_all()
    stock = db.session.scalar(db.select(Inventory).filter_by(store_id=store.id, product_id=sugar.id))
    assert stock.qty_on_hand == Decimal("15") and stock.avg_cost == Decimal("40.0000")
    assert db.session.get(PurchaseOrder, po_id).status.value == "cancelled"
    invoices = {i.invoice_number: i.payment_status.value for i in db.session.scalars(db.select(SupplierInvoice))}
    assert invoices["INV-889"] != "cancelled"  # the corrected bill keeps the number
    assert any(n.startswith("INV-889~") and s == "cancelled" for n, s in invoices.items())


def test_correcting_refused_once_goods_are_sold(client, admin_headers, store, supplier):
    from app.models.inventory import StockBatch
    sugar = make_product(store, name="Sugar", price="45.00", stock=0)
    po_id = _post(client, admin_headers, _bill(
        supplier, store, {"product_id": sugar.id, "qty": "20", "unit_price": "42"})).get_json()["purchase_order"]["id"]
    batch = db.session.scalar(db.select(StockBatch).filter_by(product_id=sugar.id, source="grn"))
    batch.qty_remaining = Decimal("18")  # 2 sold
    db.session.commit()

    assert client.get(f"/api/v1/purchases/{po_id}/direct", headers=admin_headers).status_code == 400
    before = _counts()
    resp = _put(client, admin_headers, po_id, _bill(
        supplier, store, {"product_id": sugar.id, "qty": "15", "unit_price": "40"}))
    assert resp.status_code == 400 and _counts() == before
