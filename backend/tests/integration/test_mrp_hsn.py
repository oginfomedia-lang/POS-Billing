"""MRP + HSN on products, "You saved" on bill/receipt, GST summary and GST-by-HSN report."""
import pytest

from app.extensions import db
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _bill(client, headers, *lines):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    for product, qty in lines:
        client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    return sid


def _pay_cash(client, headers, sid):
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "10000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_product_mrp_and_hsn_create_update_clear(client, admin_headers):
    body = {"name": "Amul Butter 100g", "price": "50", "tax_rate": "12", "mrp": "58", "hsn_code": "0405"}
    resp = client.post("/api/v1/products", json=body, headers=admin_headers)
    assert resp.status_code == 201, resp.get_json()
    p = resp.get_json()
    assert p["mrp"] == "58.00" and p["hsn_code"] == "0405"

    # Leaving the fields out keeps them; sending null clears them.
    kept = client.put(f"/api/v1/products/{p['id']}", json={"name": "Amul Butter"}, headers=admin_headers).get_json()
    assert kept["mrp"] == "58.00" and kept["hsn_code"] == "0405"
    cleared = client.put(f"/api/v1/products/{p['id']}", json={"mrp": None, "hsn_code": ""}, headers=admin_headers)
    assert cleared.get_json()["mrp"] is None and cleared.get_json()["hsn_code"] is None


def test_mrp_below_price_with_gst_is_rejected(client, admin_headers):
    # 50 + 12% = 56.00 > MRP 55
    resp = client.post("/api/v1/products", json={"name": "X", "price": "50", "tax_rate": "12", "mrp": "55"}, headers=admin_headers)
    assert resp.status_code == 400
    assert "MRP" in resp.get_json()["error"]["message"]

    ok = client.post("/api/v1/products", json={"name": "Y", "price": "50", "tax_rate": "12", "mrp": "60"}, headers=admin_headers)
    pid = ok.get_json()["id"]
    # Raising the price above MRP is refused too, and nothing is saved.
    resp = client.put(f"/api/v1/products/{pid}", json={"price": "55"}, headers=admin_headers)
    assert resp.status_code == 400
    assert client.get(f"/api/v1/products/{pid}", headers=admin_headers).get_json()["price"] == "50.00"


def test_bad_hsn_code(client, admin_headers):
    resp = client.post("/api/v1/products", json={"name": "X", "price": "5", "hsn_code": "12AB"}, headers=admin_headers)
    assert resp.status_code in (400, 422)


def test_bill_and_receipt_show_saving_and_gst_summary(client, cashier_headers, shift, store):
    butter = make_product(store, name="Butter", price="50.00", tax_rate="5.00", mrp="60.00", hsn_code="0405")
    soap = make_product(store, name="Soap", price="20.00", tax_rate="18.00", hsn_code="3401")  # no MRP
    sid = _bill(client, cashier_headers, (butter, 2), (soap, 1))
    paid = _pay_cash(client, cashier_headers, sid)
    lines = {i["product_name"]: i for i in paid["items"]}
    assert lines["Butter"]["mrp"] == "60.00" and lines["Butter"]["hsn_code"] == "0405"
    assert lines["Butter"]["saving"] == "15.00"  # 2 × 60 − (100 + 5.00 GST)
    assert lines["Soap"]["saving"] == "0.00"
    assert paid["total_saving"] == "15.00"

    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert receipt["total_saving"] == "15.00"
    gst = {r["tax_rate"]: r for r in receipt["gst_summary"]}
    assert gst["5.00"] == {"tax_rate": "5.00", "taxable": "100.00", "cgst": "2.50", "sgst": "2.50", "tax": "5.00"}
    assert gst["18.00"]["taxable"] == "20.00" and gst["18.00"]["tax"] == "3.60"


def test_bill_keeps_mrp_snapshot(client, cashier_headers, shift, store):
    p = make_product(store, price="50.00", tax_rate="0", mrp="60.00")
    sid = _bill(client, cashier_headers, (p, 1))
    _pay_cash(client, cashier_headers, sid)
    p.mrp = 99
    db.session.commit()
    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert receipt["items"][0]["mrp"] == "60.00"


def test_gst_report_by_hsn(client, admin_headers, cashier_headers, shift, store):
    a = make_product(store, price="100.00", tax_rate="5.00", hsn_code="0401")
    b = make_product(store, price="100.00", tax_rate="5.00")  # no HSN
    _pay_cash(client, cashier_headers, _bill(client, cashier_headers, (a, 2), (b, 1)))
    report = client.get("/api/v1/reports/sales", headers=admin_headers).get_json()
    rows = report["gst_hsn"]
    assert rows[0] == {"hsn_code": "0401", "tax_rate": "5.00", "taxable": "200.00", "tax": "10.00", "cgst": "5.00", "sgst": "5.00"}
    assert rows[-1]["hsn_code"] is None and rows[-1]["taxable"] == "100.00"
