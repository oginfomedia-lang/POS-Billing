"""Profit report: weighted-average cost from goods receipts, cost saved on bills and returns, admin only."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.inventory import Inventory
from app.models.supplier import Supplier
from tests.factories import make_counter, make_product, make_shift, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store), opening_float="500.00")


@pytest.fixture
def manager(store):
    return make_user(role="manager", username="mgr", pin="4321", store=store)


@pytest.fixture
def manager_headers(client, manager):
    token = client.post("/api/v1/auth/login", json={"username": "mgr", "pin": "4321"}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _receive(client, headers, store, product, qty, price, discount="0"):
    supplier = db.session.scalar(db.select(Supplier)) or Supplier(
        supplier_code="SUP-AAA111", company_name="Sharma Traders", payment_terms=PaymentTerms.NET_30
    )
    db.session.add(supplier)
    db.session.commit()
    po = client.post("/api/v1/purchases", json={
        "supplier_id": supplier.id, "store_id": store.id, "purchase_date": str(date.today()),
        "items": [{"product_id": product.id, "ordered_qty": qty, "unit_price": price, "tax_rate": "5",
                   "discount_percent": discount}],
    }, headers=headers).get_json()
    assert client.post(f"/api/v1/purchases/{po['id']}/place", headers=headers).status_code == 200
    item = {"purchase_order_item_id": po["items"][0]["id"], "qty_received": qty}
    resp = client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [item]}, headers=headers)
    assert resp.status_code == 201, resp.get_json()


def _avg_cost(store, product):
    db.session.expire_all()
    return db.session.scalar(
        db.select(Inventory.avg_cost).filter_by(store_id=store.id, product_id=product.id)
    )


def _sell(client, headers, *lines):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    for product, qty in lines:
        client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "10000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _set_cost(client, headers, product, cost):
    resp = client.put(f"/api/v1/products/{product.id}", json={"cost_price": cost}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_goods_receipts_keep_a_weighted_average_cost(client, admin_headers, store):
    oil = make_product(store, name="Oil", price="150.00", stock=0)
    _receive(client, admin_headers, store, oil, 10, "100")
    assert _avg_cost(store, oil) == Decimal("100.0000")
    # 10 more at ₹130 less 10% = ₹117: (10 × 100 + 10 × 117) / 20
    _receive(client, admin_headers, store, oil, 10, "130", discount="10")
    assert _avg_cost(store, oil) == Decimal("108.5000")

    listed = client.get(f"/api/v1/products?store_id={store.id}&q=Oil", headers=admin_headers).get_json()["items"][0]
    assert listed["store_avg_cost"] == "108.5000" and listed["cost_price"] is None


def test_first_receipt_averages_with_the_default_cost(client, admin_headers, store):
    dal = make_product(store, name="Dal", price="120.00", stock=10)
    _set_cost(client, admin_headers, dal, "90")
    _receive(client, admin_headers, store, dal, 10, "100")
    assert _avg_cost(store, dal) == Decimal("95.0000")


def test_profit_report(client, admin_headers, cashier_headers, shift, store, manager):
    milk = make_product(store, name="Milk", price="50.00")
    sugar = make_product(store, name="Sugar", price="40.00", is_variable_weight=True)
    rice = make_product(store, name="Rice", price="200.00")  # no cost price
    _set_cost(client, admin_headers, milk, "40")
    _set_cost(client, admin_headers, sugar, "30")

    bill = _sell(client, cashier_headers, (milk, 2), (sugar, "2.5"), (rice, 1))
    assert {i["product_name"] for i in bill["items"]} == {"Milk", "Sugar", "Rice"}
    _set_cost(client, admin_headers, milk, "45")  # later cost changes don't touch bills already made
    milk_line = next(i for i in bill["items"] if i["product_name"] == "Milk")
    body = {"bill_number": bill["bill_number"], "lines": [{"sale_item_id": milk_line["id"], "qty": 1}],
            "reason": "Spoilt", "approver_username": "mgr", "approver_pin": "4321"}
    assert client.post("/api/v1/returns", json=body, headers=cashier_headers).status_code == 201

    r = client.get(f"/api/v1/reports/profit?store_id={store.id}", headers=admin_headers)
    assert r.status_code == 200, r.get_json()
    r = r.get_json()
    s = r["summary"]
    # Milk 1 × (50 − 40) = 10; Sugar 2.5 kg × (40 − 30) = 25. Rice has no cost: shown, not counted.
    assert (s["net_sales"], s["returns"], s["costed_sales"], s["cogs"], s["gross_profit"], s["margin_pct"]) == (
        "350.00", "50.00", "150.00", "115.00", "35.00", "23.33"
    )
    assert (s["uncosted_sales"], s["uncosted_products"]) == ("200.00", 1)
    rows = {p["product_name"]: p for p in r["products"]}
    assert [p["product_name"] for p in r["products"]] == ["Sugar", "Milk"]
    assert (rows["Milk"]["qty"], rows["Milk"]["net_sales"], rows["Milk"]["cogs"], rows["Milk"]["gross_profit"]) == (
        "1", "50.00", "40.00", "10.00"
    )
    assert (rows["Sugar"]["qty"], rows["Sugar"]["cogs"], rows["Sugar"]["margin_pct"]) == ("2.5", "75.00", "25.00")
    assert [(u["product_name"], u["net_sales"]) for u in r["uncosted"]] == [("Rice", "200.00")]
    assert r["by_category"] == [
        {"category": None, "net_sales": "150.00", "cogs": "115.00", "gross_profit": "35.00", "margin_pct": "23.33"}
    ]


def test_sold_below_cost_shows_a_loss(client, admin_headers, cashier_headers, shift, store):
    soap = make_product(store, name="Soap", price="20.00")
    _set_cost(client, admin_headers, soap, "25")
    _sell(client, cashier_headers, (soap, 2))
    row = client.get(f"/api/v1/reports/profit?store_id={store.id}", headers=admin_headers).get_json()["products"][0]
    assert (row["gross_profit"], row["margin_pct"]) == ("-10.00", "-25.00")


def test_cost_and_profit_are_admin_only(client, admin_headers, manager_headers, cashier_headers, store):
    tea = make_product(store, name="Tea", price="100.00")
    _set_cost(client, admin_headers, tea, "70")

    assert client.get("/api/v1/reports/profit", headers=manager_headers).status_code == 403
    assert client.get("/api/v1/reports/profit", headers=cashier_headers).status_code == 403

    seen = client.get(f"/api/v1/products/{tea.id}", headers=manager_headers).get_json()
    assert seen["cost_price"] is None and seen["store_avg_cost"] is None
    # A manager can still edit the product, but a cost they send is ignored.
    client.put(f"/api/v1/products/{tea.id}", json={"name": "Tea 250g", "cost_price": "1"}, headers=manager_headers)
    admin_view = client.get(f"/api/v1/products/{tea.id}", headers=admin_headers).get_json()
    assert (admin_view["name"], admin_view["cost_price"]) == ("Tea 250g", "70.0000")
