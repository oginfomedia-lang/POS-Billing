"""Automatic discounts while billing, and discount admin."""
import pytest

from app.extensions import db
from app.models.category import Category
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _discount(client, headers, **fields):
    body = {"name": "Promo", "discount_type": "percentage", "value": "10", "scope": "bill", **fields}
    resp = client.post("/api/v1/discounts", json=body, headers=headers)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _bill(client, headers, *lines):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    data = None
    for product, qty in lines:
        data = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers).get_json()
    return data


def test_product_discount_reduces_taxable_value(client, admin_headers, cashier_headers, shift, store):
    milk = make_product(store, name="Milk", price="50.00", tax_rate="5.00")
    _discount(client, admin_headers, scope="product", product_id=milk.id, discount_type="fixed", value="5")
    sale = _bill(client, cashier_headers, (milk, 2))
    item = sale["items"][0]
    assert item["line_total"] == "100.00"
    assert item["discount_amount"] == "10.00"
    assert item["tax_amount"] == "4.50"  # 5% of 90
    assert (sale["subtotal"], sale["discount_amount"], sale["tax_amount"], sale["total"]) == ("100.00", "10.00", "4.50", "94.50")


def test_category_discount_and_best_one_wins(client, admin_headers, cashier_headers, shift, store):
    dairy = Category(name="Dairy")
    db.session.add(dairy)
    db.session.commit()
    milk = make_product(store, name="Milk", price="100.00", tax_rate="0")
    milk.category_id = dairy.id
    db.session.commit()
    _discount(client, admin_headers, scope="category", category_id=dairy.id, value="10")
    _discount(client, admin_headers, scope="product", product_id=milk.id, value="20")
    sale = _bill(client, cashier_headers, (milk, 1))
    assert sale["discount_amount"] == "20.00"  # not stacked: best of 10% and 20%


def test_bill_discount_with_minimum_is_spread_across_lines(client, admin_headers, cashier_headers, shift, store):
    a = make_product(store, name="A", price="300.00", tax_rate="0")
    b = make_product(store, name="B", price="100.00", tax_rate="18")
    _discount(client, admin_headers, scope="bill", discount_type="fixed", value="40", min_bill_amount="500")

    sale = _bill(client, cashier_headers, (a, 1), (b, 1))
    assert sale["discount_amount"] == "0.00"  # 400 < 500 minimum

    sid = sale["id"]
    sale = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": b.id, "qty": 1}, headers=cashier_headers).get_json()
    # subtotal 500 -> 40 off split 300:200 -> A 24, B 16; GST 18% on (200 - 16)
    shares = {i["product_name"]: i["discount_amount"] for i in sale["items"]}
    assert shares == {"A": "24.00", "B": "16.00"}
    assert sale["tax_amount"] == "33.12"
    assert sale["total"] == "493.12"


def test_inactive_and_expired_discounts_ignored(client, admin_headers, cashier_headers, shift, store):
    p = make_product(store, price="100.00", tax_rate="0")
    _discount(client, admin_headers, value="50", is_active=False)
    _discount(client, admin_headers, value="30", ends_at="2020-01-01T00:00:00+05:30")
    _discount(client, admin_headers, value="20", starts_at="2099-01-01T00:00:00+05:30")
    assert _bill(client, cashier_headers, (p, 1))["discount_amount"] == "0.00"


def test_completed_bill_keeps_discount(client, admin_headers, cashier_headers, shift, store):
    p = make_product(store, price="100.00", tax_rate="0")
    _discount(client, admin_headers, value="10")
    sid = _bill(client, cashier_headers, (p, 1))["id"]
    sale = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "card"}, headers=cashier_headers).get_json()
    assert sale["total"] == "90.00"
    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert receipt["discount_amount"] == "10.00"


def test_discount_validation(client, admin_headers):
    bad = [
        {"discount_type": "percentage", "value": "150", "scope": "bill"},
        {"discount_type": "fixed", "value": "5", "scope": "product"},  # no product
        {"discount_type": "fixed", "value": "0", "scope": "bill"},
    ]
    for body in bad:
        resp = client.post("/api/v1/discounts", json={"name": "x", **body}, headers=admin_headers)
        assert resp.status_code == 422, body


def test_update_and_list_discount(client, admin_headers, cashier_headers):
    d = _discount(client, admin_headers)
    resp = client.put(f"/api/v1/discounts/{d['id']}", json={**d, "value": "15", "is_active": False}, headers=admin_headers)
    assert resp.status_code == 200
    listed = client.get("/api/v1/discounts", headers=admin_headers).get_json()
    assert listed[0]["value"] == "15.00" and listed[0]["is_active"] is False
    assert client.get("/api/v1/discounts", headers=cashier_headers).status_code == 403
