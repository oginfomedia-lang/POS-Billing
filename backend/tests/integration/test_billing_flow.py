"""Scan -> merge qty -> pay -> complete -> stock deducted."""
import pytest

from app.extensions import db
from app.models.inventory import Inventory
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def counter(store):
    return make_counter(store, code="C01")


@pytest.fixture
def shift(cashier_user, counter):
    return make_shift(cashier_user, counter)


@pytest.fixture
def product(store):
    return make_product(store, name="Milk 1L", price="50.00", gst_rate="5.00", stock=10)


def _draft(client, headers):
    resp = client.post("/api/v1/sales", headers=headers)
    assert resp.status_code in (200, 201), resp.get_json()
    return resp.get_json()


def _stock(store, product) -> int:
    db.session.expire_all()
    return db.session.scalar(
        db.select(Inventory.qty_on_hand).where(
            Inventory.store_id == store.id, Inventory.product_id == product.id
        )
    )


def test_create_sale_without_shift_is_409(client, cashier_headers):
    resp = client.post("/api/v1/sales", headers=cashier_headers)
    assert resp.status_code == 409


def test_create_sale_reuses_open_draft(client, cashier_headers, shift):
    first = client.post("/api/v1/sales", headers=cashier_headers)
    second = client.post("/api/v1/sales", headers=cashier_headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.get_json()["id"] == second.get_json()["id"]


def test_full_cash_checkout(client, cashier_headers, shift, store, product):
    sale = _draft(client, cashier_headers)
    sid = sale["id"]

    # Scanning the same product twice merges into one line.
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": 1}, headers=cashier_headers)
    resp = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": 2}, headers=cashier_headers)
    data = resp.get_json()
    assert resp.status_code == 200
    assert len(data["items"]) == 1
    assert data["items"][0]["qty"] == 3
    assert data["subtotal"] == "150.00"
    assert data["tax_amount"] == "7.50"
    assert data["total"] == "157.50"

    # Short cash is rejected.
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "100"}, headers=cashier_headers)
    assert resp.status_code == 400

    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "200"}, headers=cashier_headers)
    data = resp.get_json()
    assert resp.status_code == 200, data
    assert data["status"] == "paid"
    assert data["bill_number"].startswith(f"ST{store.id:02d}-C01-")
    assert data["bill_number"].endswith("-0001")
    assert data["payments"][0]["change_due"] == "42.50"
    assert _stock(store, product) == 7

    # Completed bills can't be completed again.
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "card"}, headers=cashier_headers)
    assert resp.status_code == 409

    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert receipt["bill_number"] == data["bill_number"]
    assert receipt["store_name"] == store.name
    assert receipt["items"][0]["product_name"] == "Milk 1L"
    assert receipt["payments"][0]["method"] == "cash"


def test_bill_numbers_increment(client, cashier_headers, shift, product):
    numbers = []
    for _ in range(2):
        sid = _draft(client, cashier_headers)["id"]
        client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id}, headers=cashier_headers)
        resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "upi", "reference": "UPI1"}, headers=cashier_headers)
        numbers.append(resp.get_json()["bill_number"])
    assert numbers[0].endswith("-0001")
    assert numbers[1].endswith("-0002")


def test_insufficient_stock_is_400_and_nothing_deducted(client, cashier_headers, shift, store, product):
    other = make_product(store, name="Bread", price="30.00", stock=5)
    sid = _draft(client, cashier_headers)["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": 11}, headers=cashier_headers)
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": other.id, "qty": 1}, headers=cashier_headers)

    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "card"}, headers=cashier_headers)
    body = resp.get_json()
    assert resp.status_code == 400
    assert body["error"]["code"] == "INSUFFICIENT_STOCK"
    assert body["error"]["details"][0]["product_id"] == product.id
    assert _stock(store, product) == 10
    assert _stock(store, other) == 5


def test_update_and_remove_item(client, cashier_headers, shift, product):
    sid = _draft(client, cashier_headers)["id"]
    data = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id}, headers=cashier_headers).get_json()
    item_id = data["items"][0]["id"]

    data = client.put(f"/api/v1/sales/{sid}/items/{item_id}", json={"qty": 4}, headers=cashier_headers).get_json()
    assert data["items"][0]["qty"] == 4
    assert data["subtotal"] == "200.00"

    resp = client.delete(f"/api/v1/sales/{sid}/items/{item_id}", headers=cashier_headers)
    assert resp.status_code == 200
    assert resp.get_json()["items"] == []
    assert resp.get_json()["total"] == "0.00"


def test_hold_list_resume(client, cashier_headers, shift, product):
    sid = _draft(client, cashier_headers)["id"]

    # Empty bills can't be held.
    assert client.post(f"/api/v1/sales/{sid}/hold", json={}, headers=cashier_headers).status_code == 400

    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id}, headers=cashier_headers)
    resp = client.post(f"/api/v1/sales/{sid}/hold", json={"note": "customer forgot wallet"}, headers=cashier_headers)
    assert resp.get_json()["status"] == "held"

    held = client.get("/api/v1/sales/held", headers=cashier_headers).get_json()
    assert [s["id"] for s in held] == [sid]
    assert held[0]["note"] == "customer forgot wallet"

    # A fresh empty draft is discarded when the held bill is resumed.
    new_id = _draft(client, cashier_headers)["id"]
    assert new_id != sid
    resp = client.post(f"/api/v1/sales/{sid}/resume", headers=cashier_headers)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "open"
    assert _draft(client, cashier_headers)["id"] == sid
    assert client.get("/api/v1/sales/held", headers=cashier_headers).get_json() == []


def test_resume_blocked_when_current_bill_has_items(client, cashier_headers, shift, product):
    held_id = _draft(client, cashier_headers)["id"]
    client.post(f"/api/v1/sales/{held_id}/items", json={"product_id": product.id}, headers=cashier_headers)
    client.post(f"/api/v1/sales/{held_id}/hold", json={}, headers=cashier_headers)

    cur_id = _draft(client, cashier_headers)["id"]
    client.post(f"/api/v1/sales/{cur_id}/items", json={"product_id": product.id}, headers=cashier_headers)
    assert client.post(f"/api/v1/sales/{held_id}/resume", headers=cashier_headers).status_code == 409


def test_void(client, cashier_headers, shift, product):
    sid = _draft(client, cashier_headers)["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id}, headers=cashier_headers)
    resp = client.post(f"/api/v1/sales/{sid}/void", headers=cashier_headers)
    assert resp.get_json()["status"] == "voided"
    # Voided bills can't be changed.
    resp = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id}, headers=cashier_headers)
    assert resp.status_code == 409


def test_other_cashier_cannot_touch_sale(client, cashier_headers, admin_headers, shift, product):
    sid = _draft(client, cashier_headers)["id"]
    resp = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id}, headers=admin_headers)
    assert resp.status_code == 403


def test_receipt_for_open_sale_is_409(client, cashier_headers, shift):
    sid = _draft(client, cashier_headers)["id"]
    assert client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).status_code == 409


def test_open_shift_endpoint(client, cashier_headers, counter):
    assert client.get("/api/v1/shifts/active", headers=cashier_headers).status_code == 404
    resp = client.post("/api/v1/shifts/open", json={"counter_code": "C01", "opening_cash": "500"}, headers=cashier_headers)
    assert resp.status_code == 201
    assert resp.get_json()["opening_cash"] == "500.00"
    assert client.get("/api/v1/shifts/active", headers=cashier_headers).status_code == 200
    resp = client.post("/api/v1/shifts/open", json={"counter_code": "C01"}, headers=cashier_headers)
    assert resp.status_code == 409
