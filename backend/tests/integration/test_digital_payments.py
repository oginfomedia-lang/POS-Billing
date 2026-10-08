"""Card / UPI through Razorpay (mock mode): exact amount, auto-complete, can't be faked, cancelled on cart change."""
import pytest

from app.extensions import db
from app.models.inventory import Inventory
from app.models.payment_intent import PaymentIntent
from app.services import razorpay_gateway
from tests.factories import make_counter, make_product, make_shift, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def counter(store):
    return make_counter(store, code="C01", edc_device_id="TEST01|ezetap_android")


@pytest.fixture
def shift(cashier_user, counter):
    return make_shift(cashier_user, counter)


@pytest.fixture
def product(store):
    return make_product(store, name="Milk 1L", price="50.00", tax_rate="0", stock=10)


def _bill(client, headers, product, qty=2):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    return sid


def _start(client, headers, sid, method):
    return client.post(f"/api/v1/sales/{sid}/payment-intents", json={"method": method}, headers=headers)


def _poll(client, headers, intent_id):
    return client.get(f"/api/v1/payment-intents/{intent_id}", headers=headers)


def _customer_pays(intent_id):
    ref = db.session.get(PaymentIntent, intent_id).provider_ref
    razorpay_gateway._mock_started[ref] = 0


def _stock(store, product):
    db.session.expire_all()
    return db.session.scalar(
        db.select(Inventory.qty_on_hand).where(Inventory.store_id == store.id, Inventory.product_id == product.id)
    )


def test_upi_qr_for_exact_amount_then_auto_complete(client, cashier_headers, shift, store, product):
    sid = _bill(client, cashier_headers, product)

    resp = _start(client, cashier_headers, sid, "upi")
    assert resp.status_code == 201, resp.get_json()
    intent = resp.get_json()
    assert intent["status"] == "pending"
    assert intent["amount"] == "100.00"  # 2 × 50, decided by the server
    assert intent["qr_image_url"]

    waiting = _poll(client, cashier_headers, intent["id"]).get_json()
    assert waiting["status"] == "pending"
    assert waiting["sale"] is None
    assert _stock(store, product) == 10

    _customer_pays(intent["id"])
    done = _poll(client, cashier_headers, intent["id"]).get_json()
    assert done["status"] == "paid"
    sale = done["sale"]
    assert sale["status"] == "paid"
    assert sale["bill_number"]
    assert sale["payments"][0]["method"] == "upi"
    assert sale["payments"][0]["amount"] == "100.00"
    assert sale["payments"][0]["reference"].startswith("mock_txn_")  # Razorpay's payment id
    assert _stock(store, product) == 8

    # Polling again is harmless: same paid bill, not a second sale.
    again = _poll(client, cashier_headers, intent["id"]).get_json()
    assert again["sale"]["bill_number"] == sale["bill_number"]


def test_card_pushes_to_counter_machine(client, cashier_headers, shift, product):
    sid = _bill(client, cashier_headers, product)
    intent = _start(client, cashier_headers, sid, "card").get_json()
    assert intent["qr_image_url"] is None
    _customer_pays(intent["id"])
    sale = _poll(client, cashier_headers, intent["id"]).get_json()["sale"]
    assert sale["payments"][0]["method"] == "card"


def test_card_without_machine_on_counter_is_400(client, cashier_user, cashier_headers, store, product):
    make_shift(cashier_user, make_counter(store, code="C02"))
    sid = _bill(client, cashier_headers, product)
    resp = _start(client, cashier_headers, sid, "card")
    assert resp.status_code == 400
    assert "No card machine" in resp.get_json()["error"]["message"]


@pytest.mark.parametrize("method", ["card", "upi"])
def test_card_or_upi_cannot_be_faked(client, cashier_headers, shift, store, product, method):
    sid = _bill(client, cashier_headers, product)
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": method}, headers=cashier_headers)
    assert resp.status_code == 400
    assert _stock(store, product) == 10

    # A pending (unpaid) intent is not enough either.
    intent = _start(client, cashier_headers, sid, method).get_json()
    resp = client.post(
        f"/api/v1/sales/{sid}/complete",
        json={"method": method, "payment_intent_id": intent["id"]},
        headers=cashier_headers,
    )
    assert resp.status_code == 400


def test_cart_change_cancels_live_qr(client, cashier_headers, shift, product):
    sid = _bill(client, cashier_headers, product)
    intent = _start(client, cashier_headers, sid, "upi").get_json()

    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": 1}, headers=cashier_headers)

    after = _poll(client, cashier_headers, intent["id"]).get_json()
    assert after["status"] == "cancelled"
    assert after["sale"] is None


def test_starting_again_replaces_old_attempt(client, cashier_headers, shift, product):
    sid = _bill(client, cashier_headers, product)
    first = _start(client, cashier_headers, sid, "upi").get_json()
    second = _start(client, cashier_headers, sid, "card").get_json()
    assert _poll(client, cashier_headers, first["id"]).get_json()["status"] == "cancelled"
    assert _poll(client, cashier_headers, second["id"]).get_json()["status"] == "pending"


def test_cancel_endpoint(client, cashier_headers, shift, product):
    sid = _bill(client, cashier_headers, product)
    intent = _start(client, cashier_headers, sid, "upi").get_json()
    resp = client.post(f"/api/v1/payment-intents/{intent['id']}/cancel", headers=cashier_headers)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cancelled"
    # The bill is still open, so the cashier can take cash instead.
    cash = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "100"}, headers=cashier_headers)
    assert cash.status_code == 200


def test_paid_but_out_of_stock_keeps_reporting_error(client, cashier_headers, shift, store):
    p = make_product(store, name="Amul Butter", price="50.00", tax_rate="0", stock=1)
    sid = _bill(client, cashier_headers, p, qty=3)
    intent = _start(client, cashier_headers, sid, "upi").get_json()
    _customer_pays(intent["id"])

    for _ in range(2):  # the retry must not pretend the bill is done
        resp = _poll(client, cashier_headers, intent["id"])
        assert resp.status_code == 400
        assert "Amul Butter" in resp.get_json()["error"]["message"]
    assert _stock(store, p) == 1


def test_other_cashier_cannot_touch_payment(client, cashier_headers, shift, store, product):
    sid = _bill(client, cashier_headers, product)
    intent = _start(client, cashier_headers, sid, "upi").get_json()

    make_user(role="cashier", username="cashier2", pin="1111", store=store)
    token = client.post("/api/v1/auth/login", json={"username": "cashier2", "pin": "1111"}).get_json()["access_token"]
    other = {"Authorization": f"Bearer {token}"}

    assert _poll(client, other, intent["id"]).status_code == 409
    assert client.post(f"/api/v1/payment-intents/{intent['id']}/cancel", headers=other).status_code == 409
