"""Manual card/UPI: the shop's own card machine / UPI QR sticker, confirmed by the cashier (no Razorpay)."""
import pytest

from app.extensions import db
from app.models.payment import Payment
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _set_mode(client, admin_headers, mode):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    resp = client.put("/api/v1/settings", json={**s, "card_upi_mode": mode}, headers=admin_headers)
    assert resp.status_code == 200 and resp.get_json()["card_upi_mode"] == mode


def _bill(client, headers, product):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": 2}, headers=headers)
    return sid


def _complete(client, headers, sid, method, reference=None):
    return client.post(f"/api/v1/sales/{sid}/complete", json={"method": method, "reference": reference}, headers=headers)


def test_default_is_razorpay(client, cashier_headers):
    assert client.get("/api/v1/sales/payment-mode", headers=cashier_headers).get_json() == {"card_upi_mode": "razorpay"}


@pytest.mark.parametrize("method", ["card", "upi"])
def test_manual_mode_completes_without_razorpay(client, admin_headers, cashier_headers, shift, store, method):
    _set_mode(client, admin_headers, "manual")
    assert client.get("/api/v1/sales/payment-mode", headers=cashier_headers).get_json() == {"card_upi_mode": "manual"}
    sid = _bill(client, cashier_headers, make_product(store, price="50.00", tax_rate="5.00"))

    resp = _complete(client, cashier_headers, sid, method, reference="UTR123456")
    assert resp.status_code == 200, resp.get_json()
    sale = resp.get_json()
    assert sale["status"] == "paid" and sale["total"] == "105.00"
    payment = db.session.scalar(db.select(Payment).filter_by(sale_id=sid))
    assert (payment.method.value, str(payment.amount), payment.reference) == (method, "105.00", "UTR123456")

    audit = client.get("/api/v1/audit-logs?action=sale.complete", headers=admin_headers).get_json()["items"]
    assert audit[0]["new_values"]["manual"] is True and audit[0]["new_values"]["method"] == method


def test_manual_mode_never_calls_razorpay(client, admin_headers, cashier_headers, shift, store):
    _set_mode(client, admin_headers, "manual")
    sid = _bill(client, cashier_headers, make_product(store))
    resp = client.post(f"/api/v1/sales/{sid}/payment-intents", json={"method": "upi"}, headers=cashier_headers)
    assert resp.status_code == 400 and "manual" in resp.get_json()["error"]["message"]


def test_razorpay_mode_still_needs_confirmation(client, admin_headers, cashier_headers, shift, store):
    _set_mode(client, admin_headers, "manual")
    _set_mode(client, admin_headers, "razorpay")
    sid = _bill(client, cashier_headers, make_product(store))
    resp = _complete(client, cashier_headers, sid, "card", reference="123")
    assert resp.status_code == 400 and "not confirmed by Razorpay" in resp.get_json()["error"]["message"]


def test_cash_unchanged_in_manual_mode(client, admin_headers, cashier_headers, shift, store):
    _set_mode(client, admin_headers, "manual")
    sid = _bill(client, cashier_headers, make_product(store, price="10.00", tax_rate="0"))
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "50"}, headers=cashier_headers)
    assert resp.status_code == 200
    audit = client.get("/api/v1/audit-logs?action=sale.complete", headers=admin_headers).get_json()["items"]
    assert "manual" not in audit[0]["new_values"]
