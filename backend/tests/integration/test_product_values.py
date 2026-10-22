"""Product prices / GST / names are checked, so no bill (and no sales report) can get a negative amount or
discount. Bad values give a clear 422, never a server error."""
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.product import Product
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _create(client, headers, **fields):
    return client.post("/api/v1/products", json={"name": "Tea", "price": "10", **fields}, headers=headers)


def _field_error(resp):
    return " ".join(d["message"] for d in resp.get_json()["error"]["details"])


@pytest.mark.parametrize("fields, message", [
    ({"price": "-25.00"}, "Selling price can't be negative"),
    ({"price": "100000000000"}, "Selling price can be at most"),
    ({"price": "abc"}, "Selling price must be a number"),
    ({"price": "NaN"}, "Selling price must be a number"),
    ({"tax_rate": "150"}, "GST rate must be between 0 and 100"),
    ({"tax_rate": "-5"}, "GST rate must be between 0 and 100"),
    ({"tax_rate": "1000"}, "GST rate must be between 0 and 100"),
    ({"mrp": "-1"}, "MRP must be between 0"),
    ({"cost_price": "1000000000"}, "Cost price can be at most"),
    ({"name": ""}, "Enter a product name"),
    ({"name": "   "}, "Enter a product name"),
    ({"name": "Q" * 250}, "at most 200 characters"),
    ({"sku": "S" * 60}, "SKU can be at most 50"),
])
def test_bad_values_are_refused_with_a_clear_message(client, admin_headers, fields, message):
    resp = _create(client, admin_headers, **fields)
    assert resp.status_code == 422, resp.get_json()
    assert message in _field_error(resp)
    assert db.session.scalar(db.select(db.func.count(Product.id))) == 0


def test_good_edge_values_are_accepted(client, admin_headers):
    free = _create(client, admin_headers, name="  Free   sample ", price="0", tax_rate="0")
    assert free.status_code == 201 and free.get_json()["name"] == "Free sample"
    assert _create(client, admin_headers, name="Gold coin", price="9999999999.99", tax_rate="100").status_code == 201


def test_editing_to_a_bad_value_is_refused(client, admin_headers):
    pid = _create(client, admin_headers).get_json()["id"]
    for body in ({"price": "-1"}, {"tax_rate": "101"}, {"name": " "}):
        assert client.put(f"/api/v1/products/{pid}", json=body, headers=admin_headers).status_code == 422
    assert client.get(f"/api/v1/products/{pid}", headers=admin_headers).get_json()["price"] == "10.00"


def test_old_product_with_a_negative_price_cannot_be_billed(client, cashier_headers, admin_headers, shift, store):
    """A product saved before these checks (here put straight into the database)."""
    bad = make_product(store, name="Old negative", price="-25.00", tax_rate="18.00")
    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    resp = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": bad.id, "qty": 2}, headers=cashier_headers)
    assert resp.status_code == 400 and "negative price" in resp.get_json()["error"]["message"]

    # Nothing negative reaches the bill or the sales report.
    good = make_product(store, name="Biscuit", price="10.00", tax_rate="0.00")
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": good.id, "qty": 1}, headers=cashier_headers)
    sale = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "10"},
                       headers=cashier_headers).get_json()
    assert (sale["subtotal"], sale["discount_amount"], sale["total"]) == ("10.00", "0.00", "10.00")
    report = client.get(f"/api/v1/reports/sales?store_id={store.id}", headers=admin_headers).get_json()["summary"]
    assert Decimal(report["discount"]) >= 0


def test_check_products_command_lists_bad_products(app, store):
    run = lambda: app.test_cli_runner().invoke(args=["check-products"])  # noqa: E731
    make_product(store, name="Fine", price="10.00")
    ok = run()
    assert ok.exit_code == 0 and "All products have a valid price" in ok.output

    make_product(store, name="Old negative", price="-25.00")
    make_product(store, name="Old GST", price="10.00", tax_rate="150.00")
    found = run()
    assert found.exit_code == 1
    assert "2 product(s) to correct" in found.output
    assert "Old negative: price -25.00" in found.output and "Old GST" in found.output and "Fine" not in found.output
