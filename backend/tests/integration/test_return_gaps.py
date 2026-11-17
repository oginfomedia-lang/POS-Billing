"""Each test describes the behaviour returns should have. Run before the fixes to prove the gap, after to prove the fix."""
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.customer import Customer
from tests.factories import make_counter, make_product, make_shift, make_user

pytestmark = pytest.mark.integration
MOBILE = "9876543210"


@pytest.fixture
def manager(store):
    return make_user(role="manager", username="mgr", pin="4321", store=store)


def _sell(client, headers, lines, mobile=None):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    for product, qty in lines:
        client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    if mobile:
        client.put(f"/api/v1/sales/{sid}/customer-mobile", json={"mobile": mobile}, headers=headers)
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "10000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _return(client, headers, sale, qty=1, restock=True):
    return client.post("/api/v1/returns", json={
        "bill_number": sale["bill_number"],
        "lines": [{"sale_item_id": sale["items"][0]["id"], "qty": qty, "restock": restock}],
        "reason": "Damaged", "approver_username": "mgr", "approver_pin": "4321",
    }, headers=headers)


def test_refund_larger_than_the_drawer_is_refused(client, cashier_headers, cashier_user, store, manager):
    counter = make_counter(store)
    first = make_shift(cashier_user, counter, opening_float="0.00")
    p = make_product(store, price="100.00", tax_rate="0")
    sale = _sell(client, cashier_headers, [(p, 1)])
    client.post(f"/api/v1/shifts/{first.id}/close", json={"actual_cash": "100"}, headers=cashier_headers)
    make_shift(cashier_user, counter, opening_float="50.00")

    resp = _return(client, cashier_headers, sale)
    assert resp.status_code == 400, resp.get_json()
    assert "Not enough cash" in resp.get_json()["error"]["message"]


def test_refund_equal_to_the_drawer_is_allowed(client, cashier_headers, cashier_user, store, manager):
    make_shift(cashier_user, make_counter(store), opening_float="0.00")
    p = make_product(store, price="100.00", tax_rate="0")
    sale = _sell(client, cashier_headers, [(p, 1)])
    assert _return(client, cashier_headers, sale).status_code == 201


@pytest.mark.parametrize("price", ["500.00", "50.00"])  # 50: small bill that earned no points
def test_return_reduces_customer_total_spent(client, cashier_headers, cashier_user, store, manager, price):
    make_shift(cashier_user, make_counter(store), opening_float="500.00")
    p = make_product(store, price=price, tax_rate="0")
    sale = _sell(client, cashier_headers, [(p, 2)], mobile=MOBILE)
    assert _return(client, cashier_headers, sale).status_code == 201
    db.session.expire_all()
    customer = db.session.scalar(db.select(Customer).filter_by(mobile=MOBILE))
    assert customer.total_spent == Decimal(price)


def test_damaged_return_keeps_its_cost_in_profit(client, admin_headers, cashier_headers, cashier_user, store, manager):
    make_shift(cashier_user, make_counter(store), opening_float="500.00")
    milk = make_product(store, name="Milk", price="50.00", tax_rate="0")
    client.put(f"/api/v1/products/{milk.id}", json={"cost_price": "40"}, headers=admin_headers)
    sale = _sell(client, cashier_headers, [(milk, 2)])
    assert _return(client, cashier_headers, sale, restock=False).status_code == 201

    s = client.get(f"/api/v1/reports/profit?store_id={store.id}", headers=admin_headers).get_json()["summary"]
    # Sold 2 (₹100), refunded 1 (₹50), both units cost ₹40 and neither can be sold again: 50 - 80.
    assert (s["net_sales"], s["cogs"], s["gross_profit"]) == ("50.00", "80.00", "-30.00")
