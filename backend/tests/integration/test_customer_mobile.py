"""Optional customer mobile on the bill: saved on the open bill, masked on the receipt, used to find bills."""
import pytest

from app.extensions import db
from app.models.enums import PaymentIntentStatus
from app.models.payment_intent import PaymentIntent
from tests.factories import make_counter, make_product, make_shift, make_store, make_user, pay_by_razorpay

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store, edc_device_id="TEST01|ezetap_android"))


def _bill(client, headers, product):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": 1}, headers=headers)
    return sid


def _set(client, headers, sid, mobile):
    return client.put(f"/api/v1/sales/{sid}/customer-mobile", json={"mobile": mobile}, headers=headers)


def _pay_cash(client, headers, sid):
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "1000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_set_clear_and_validate(client, cashier_headers, shift, store):
    sid = _bill(client, cashier_headers, make_product(store))

    resp = _set(client, cashier_headers, sid, "+91 98765-43210")
    assert resp.status_code == 200 and resp.get_json()["customer_mobile"] == "9876543210"

    bad = _set(client, cashier_headers, sid, "12345")
    assert bad.status_code == 400 and "10-digit" in bad.get_json()["error"]["message"]

    assert _set(client, cashier_headers, sid, None).get_json()["customer_mobile"] is None


def test_receipt_is_masked_and_bill_is_locked(client, cashier_headers, shift, store):
    sid = _bill(client, cashier_headers, make_product(store))
    _set(client, cashier_headers, sid, "9876543210")
    paid = _pay_cash(client, cashier_headers, sid)
    assert paid["customer_mobile"] == "9876543210"  # staff screens: full number

    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert receipt["customer_mobile"] == "98XXXXX210"  # printed slip: masked

    assert _set(client, cashier_headers, sid, "9123456789").status_code == 409  # paid bills can't change


def test_bill_without_mobile_completes(client, cashier_headers, shift, store):
    sid = _bill(client, cashier_headers, make_product(store))
    paid = _pay_cash(client, cashier_headers, sid)
    assert paid["customer_mobile"] is None
    assert client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()["customer_mobile"] is None


def test_mobile_set_during_upi_payment_keeps_the_qr(client, cashier_headers, shift, store):
    sid = _bill(client, cashier_headers, make_product(store))
    intent = client.post(f"/api/v1/sales/{sid}/payment-intents", json={"method": "upi"}, headers=cashier_headers).get_json()

    _set(client, cashier_headers, sid, "9876543210")
    db.session.expire_all()
    assert db.session.get(PaymentIntent, intent["id"]).status is PaymentIntentStatus.PENDING  # QR still live

    paid = pay_by_razorpay(client, cashier_headers, sid, "upi").get_json()["sale"]
    assert paid["customer_mobile"] == "9876543210"


def test_find_bills_by_mobile(client, cashier_headers, shift, store):
    p = make_product(store, price="10.00", tax_rate="0")
    first = _bill(client, cashier_headers, p)
    _set(client, cashier_headers, first, "9876543210")
    first_no = _pay_cash(client, cashier_headers, first)["bill_number"]
    second = _bill(client, cashier_headers, p)
    _set(client, cashier_headers, second, "98765 43210")
    second_no = _pay_cash(client, cashier_headers, second)["bill_number"]
    other = _bill(client, cashier_headers, p)
    _set(client, cashier_headers, other, "9000000000")
    _pay_cash(client, cashier_headers, other)

    bills = client.get("/api/v1/returns/bills?mobile=+919876543210", headers=cashier_headers).get_json()
    assert [b["bill_number"] for b in bills] == [second_no, first_no]  # newest first
    assert bills[0]["items_count"] == 1 and bills[0]["total"] == "10.00"

    assert client.get("/api/v1/returns/bills?mobile=9111111111", headers=cashier_headers).get_json() == []
    assert client.get("/api/v1/returns/bills?mobile=123", headers=cashier_headers).status_code == 400


def test_find_bills_is_own_store_only(client, cashier_headers, shift, store):
    other_store = make_store(name="Other")
    other_cashier = make_user(role="cashier", username="c2", pin="1111", store=other_store)
    make_shift(other_cashier, make_counter(other_store, code="X01"))
    token = client.post("/api/v1/auth/login", json={"username": "c2", "pin": "1111"}).get_json()["access_token"]
    other_headers = {"Authorization": f"Bearer {token}"}

    sid = _bill(client, other_headers, make_product(other_store, price="10.00", tax_rate="0"))
    _set(client, other_headers, sid, "9876543210")
    _pay_cash(client, other_headers, sid)

    assert client.get("/api/v1/returns/bills?mobile=9876543210", headers=cashier_headers).get_json() == []
    assert len(client.get("/api/v1/returns/bills?mobile=9876543210", headers=other_headers).get_json()) == 1
