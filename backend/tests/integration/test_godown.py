"""Godown vs shop shelf: GRN into the godown, moving to the shelf, sales never blocked, refill list, stock-take."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.inventory import Inventory, StockTransfer
from app.models.supplier import Supplier
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def godown_on(client, admin_headers):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    assert client.put("/api/v1/settings", json={**s, "godown_enabled": True}, headers=admin_headers).status_code == 200


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store), opening_float="500.00")


def _row(store, product):
    db.session.expire_all()
    return db.session.scalar(db.select(Inventory).filter_by(store_id=store.id, product_id=product.id))


def _levels(client, headers, store, product):
    rows = client.get(f"/api/v1/inventory?store_id={store.id}", headers=headers).get_json()
    return next(r for r in rows if r["product_id"] == product.id)


def _receive(client, headers, store, product, qty, to_shop=False):
    supplier = Supplier(supplier_code=f"SUP-G{product.id}", company_name="Sharma Traders",
                        payment_terms=PaymentTerms.NET_30)
    db.session.add(supplier)
    db.session.commit()
    po = client.post("/api/v1/purchases", json={
        "supplier_id": supplier.id, "store_id": store.id, "purchase_date": str(date.today()),
        "items": [{"product_id": product.id, "ordered_qty": qty, "unit_price": "20", "tax_rate": "0"}],
    }, headers=headers).get_json()
    client.post(f"/api/v1/purchases/{po['id']}/place", headers=headers)
    item = {"purchase_order_item_id": po["items"][0]["id"], "qty_received": qty, "to_shop": to_shop}
    resp = client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [item]}, headers=headers)
    assert resp.status_code == 201, resp.get_json()


def _move(client, headers, store, product, qty, direction="to_shop"):
    return client.post("/api/v1/inventory/transfer", json={
        "store_id": store.id, "product_id": product.id, "qty": qty, "direction": direction,
    }, headers=headers)


def _sell(client, headers, product, qty):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    return client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "10000"},
                       headers=headers)


def test_grn_goes_to_godown_only_when_switched_on(client, admin_headers, store):
    salt = make_product(store, name="Salt", stock=0)
    _receive(client, admin_headers, store, salt, "100")
    assert _row(store, salt).godown_qty == 0  # off: everything on the shelf, as before

    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    client.put("/api/v1/settings", json={**s, "godown_enabled": True}, headers=admin_headers)
    sugar = make_product(store, name="Sugar", stock=0)
    _receive(client, admin_headers, store, sugar, "100")
    lv = _levels(client, admin_headers, store, sugar)
    assert (lv["qty_on_hand"], lv["godown_qty"], lv["shop_qty"]) == ("100.000", "100.000", "0.000")


def test_straight_to_shelf_line(client, admin_headers, store, godown_on):
    milk = make_product(store, name="Milk", stock=0)
    _receive(client, admin_headers, store, milk, "20", to_shop=True)
    assert _row(store, milk).godown_qty == 0


def test_move_to_shelf_and_back(client, admin_headers, store, godown_on):
    salt = make_product(store, name="Salt", stock=0)
    _receive(client, admin_headers, store, salt, "100")
    assert _move(client, admin_headers, store, salt, "15").status_code == 200
    row = _row(store, salt)
    assert (row.qty_on_hand, row.godown_qty) == (Decimal("100"), Decimal("85"))  # total unchanged

    too_many = _move(client, admin_headers, store, salt, "86")
    assert too_many.status_code == 400 and "Only 85 in the godown" in too_many.get_json()["error"]["message"]
    assert _move(client, admin_headers, store, salt, "5", "to_godown").status_code == 200
    assert _row(store, salt).godown_qty == Decimal("90")
    assert _move(client, admin_headers, store, salt, "11", "to_godown").status_code == 400  # shelf has only 10


def test_sale_uses_shelf_then_godown_and_is_never_blocked(client, admin_headers, cashier_headers, shift, store,
                                                          godown_on):
    salt = make_product(store, name="Salt", stock=0)
    _receive(client, admin_headers, store, salt, "100")
    _move(client, admin_headers, store, salt, "3")  # shelf 3, godown 97

    assert _sell(client, cashier_headers, salt, 2).status_code == 200  # from the shelf
    row = _row(store, salt)
    assert (row.qty_on_hand, row.godown_qty) == (Decimal("98"), Decimal("97"))

    # Staff refilled the shelf but didn't tell the app: the bill still goes through.
    resp = _sell(client, cashier_headers, salt, 5)
    assert resp.status_code == 200, resp.get_json()
    row = _row(store, salt)
    assert (row.qty_on_hand, row.godown_qty) == (Decimal("93"), Decimal("93"))  # shelf 0
    auto = db.session.scalar(db.select(StockTransfer).filter_by(reason="auto_sale"))
    assert auto.qty == Decimal("4") and auto.reference_id == resp.get_json()["id"]

    # Only the WHOLE stock running out blocks a bill, exactly as before.
    assert _sell(client, cashier_headers, salt, 94).status_code != 200


def test_refill_list(client, admin_headers, store, godown_on):
    salt = make_product(store, name="Salt", stock=0)
    _receive(client, admin_headers, store, salt, "100")
    _move(client, admin_headers, store, salt, "2")
    client.post("/api/v1/inventory/shelf-min", json={"store_id": store.id, "product_id": salt.id,
                                                      "shelf_min_qty": "3"}, headers=admin_headers)
    rows = client.get(f"/api/v1/inventory/refill?store_id={store.id}", headers=admin_headers).get_json()
    assert [(r["product_name"], r["shop_qty"], r["godown_qty"]) for r in rows] == [("Salt", "2.000", "98.000")]
    assert _levels(client, admin_headers, store, salt)["needs_refill"] is True

    _move(client, admin_headers, store, salt, "10")
    assert client.get(f"/api/v1/inventory/refill?store_id={store.id}", headers=admin_headers).get_json() == []


def test_returns_go_back_on_the_shelf(client, admin_headers, cashier_headers, shift, store, godown_on):
    from tests.factories import make_user

    make_user(role="manager", username="mgr", pin="4321", store=store)
    salt = make_product(store, name="Salt", stock=0)
    _receive(client, admin_headers, store, salt, "10")
    _move(client, admin_headers, store, salt, "4")
    sale = _sell(client, cashier_headers, salt, 2).get_json()
    client.post("/api/v1/returns", json={
        "bill_number": sale["bill_number"], "lines": [{"sale_item_id": sale["items"][0]["id"], "qty": 1}],
        "reason": "Changed mind", "approver_username": "mgr", "approver_pin": "4321",
    }, headers=cashier_headers)
    lv = _levels(client, admin_headers, store, salt)
    assert (lv["shop_qty"], lv["godown_qty"]) == ("3.000", "6.000")


def test_stock_take_by_place(client, admin_headers, store, godown_on):
    salt = make_product(store, name="Salt", stock=0)
    _receive(client, admin_headers, store, salt, "100")
    _move(client, admin_headers, store, salt, "20")  # shelf 20, godown 80

    def count(qty, location=None):
        body = {"store_id": store.id, "product_id": salt.id, "new_qty": qty, "notes": "Stock-take"}
        if location:
            body["location"] = location
        assert client.post("/api/v1/inventory/adjust", json=body, headers=admin_headers).status_code == 200
        row = _row(store, salt)
        return row.qty_on_hand - row.godown_qty, row.godown_qty

    assert count("75", "godown") == (Decimal("20"), Decimal("75"))  # 5 missing in the godown
    assert count("18", "shop") == (Decimal("18"), Decimal("75"))
    assert count("50") == (Decimal("0"), Decimal("50"))  # whole count below the godown figure


def test_write_off_from_godown(client, admin_headers, store, godown_on):
    salt = make_product(store, name="Salt", stock=0)
    _receive(client, admin_headers, store, salt, "10")
    _move(client, admin_headers, store, salt, "4")  # shelf 4, godown 6
    batch = client.get(f"/api/v1/inventory/batches?store_id={store.id}&product_id={salt.id}",
                       headers=admin_headers).get_json()[0]
    resp = client.post(f"/api/v1/inventory/batches/{batch['id']}/write-off",
                       json={"qty": "2", "reason": "Rats", "from_godown": True}, headers=admin_headers)
    assert resp.status_code == 200, resp.get_json()
    row = _row(store, salt)
    assert (row.qty_on_hand - row.godown_qty, row.godown_qty) == (Decimal("4"), Decimal("4"))
