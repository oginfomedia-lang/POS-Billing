"""Shift open/close and cash difference tests."""
import pytest

from tests.factories import make_counter, make_product, make_store, pay_by_razorpay

pytestmark = pytest.mark.integration


def test_open_shift_with_counter_puts_code_on_bill(client, cashier_headers, store):
    counter = make_counter(store, code="C03")
    product = make_product(store)
    resp = client.post(
        "/api/v1/shifts/open",
        json={"store_id": store.id, "counter_id": counter.id, "opening_float": 500},
        headers=cashier_headers,
    )
    assert resp.status_code == 201
    assert resp.get_json()["counter_id"] == counter.id

    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id}, headers=cashier_headers)
    sale = pay_by_razorpay(client, cashier_headers, sid, "upi").get_json()["sale"]
    assert sale["bill_number"].startswith(f"ST{store.id:02d}-C03-")


def test_open_shift_rejects_counter_from_other_store(client, cashier_headers, store):
    other = make_counter(make_store(name="Other"), code="X01")
    resp = client.post(
        "/api/v1/shifts/open",
        json={"store_id": store.id, "counter_id": other.id},
        headers=cashier_headers,
    )
    assert resp.status_code == 404


def test_open_shift_rejects_inactive_counter(client, cashier_headers, store):
    counter = make_counter(store, code="C09", is_active=False)
    resp = client.post(
        "/api/v1/shifts/open",
        json={"store_id": store.id, "counter_id": counter.id},
        headers=cashier_headers,
    )
    assert resp.status_code == 404
