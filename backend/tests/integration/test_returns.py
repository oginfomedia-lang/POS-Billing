"""Returns: cash refund, manager PIN, 30-day window, proportional amounts, restock, shift cash and reports."""
from datetime import timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.enums import InventoryTxnType
from app.models.inventory import Inventory, InventoryTransaction
from app.models.sale import Sale
from app.utils.dates import now_ist
from tests.factories import make_counter, make_product, make_shift, make_store, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store), opening_float="500.00")


@pytest.fixture
def manager(store):
    return make_user(role="manager", username="mgr", pin="4321", store=store)


def _sell(client, headers, *lines):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    for product, qty in lines:
        client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "10000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _lookup(client, headers, bill_number):
    return client.get(f"/api/v1/returns/bill/{bill_number}", headers=headers)


def _return(client, headers, bill_number, lines, pin="4321", username="mgr", reason="Damaged"):
    body = {
        "bill_number": bill_number,
        "lines": lines,
        "reason": reason,
        "approver_username": username,
        "approver_pin": pin,
    }
    return client.post("/api/v1/returns", json=body, headers=headers)


def _line(bill, name):
    return next(ln for ln in bill["lines"] if ln["product_name"] == name)


def _stock(store, product):
    db.session.expire_all()
    return db.session.scalar(
        db.select(Inventory.qty_on_hand).where(Inventory.store_id == store.id, Inventory.product_id == product.id)
    )


def test_lookup_shows_returnable_lines(client, cashier_headers, shift, store):
    p = make_product(store, name="Milk", price="50.00", tax_rate="5.00")
    sale = _sell(client, cashier_headers, (p, 2))

    resp = _lookup(client, cashier_headers, sale["bill_number"])
    assert resp.status_code == 200, resp.get_json()
    bill = resp.get_json()
    assert bill["can_return"] is True and bill["days_left"] == 30
    assert bill["payment_methods"] == ["cash"]
    line = _line(bill, "Milk")
    assert line["qty_sold"] == 2 and line["qty_returnable"] == 2

    assert _lookup(client, cashier_headers, "NOPE-123").status_code == 404


def test_partial_then_rest_adds_up_exactly(client, cashier_headers, shift, store, manager):
    p = make_product(store, name="Soap", price="9.99", tax_rate="18.00")
    sale = _sell(client, cashier_headers, (p, 3))  # line 29.97, GST 5.39 -> 35.36
    item_id = sale["items"][0]["id"]

    first = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": item_id, "qty": 1}])
    assert first.status_code == 201, first.get_json()
    r1 = first.get_json()
    assert r1["return_number"].startswith(f"RT{store.id:02d}-")
    assert r1["items"][0]["line_total"] == "9.99" and r1["items"][0]["tax_amount"] == "1.80"
    assert r1["refund_amount"] == "11.79"
    assert r1["approved_by_name"] == "Test User" and r1["refund_method"] == "cash"

    rest = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": item_id, "qty": 2}]).get_json()
    # The last units take exactly what is left: 29.97 - 9.99 and 5.39 - 1.80.
    assert rest["items"][0]["line_total"] == "19.98" and rest["items"][0]["tax_amount"] == "3.59"
    assert Decimal(r1["refund_amount"]) + Decimal(rest["refund_amount"]) == Decimal(sale["total"])

    bill = _lookup(client, cashier_headers, sale["bill_number"]).get_json()
    assert bill["can_return"] is False and "already been returned" in bill["blocked_reason"]


def test_offer_discount_is_reversed_proportionally(client, admin_headers, cashier_headers, shift, store, manager):
    p = make_product(store, name="Rice", price="100.00", tax_rate="0")
    client.post(
        "/api/v1/discounts",
        json={"name": "10% off", "discount_type": "percentage", "value": "10", "scope": "bill"},
        headers=admin_headers,
    )
    sale = _sell(client, cashier_headers, (p, 2))  # 200 - 20 = 180
    assert sale["total"] == "180.00"
    r = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": sale["items"][0]["id"], "qty": 1}])
    assert r.get_json()["refund_amount"] == "90.00"  # customer gets back what they actually paid


def test_over_return_and_bad_lines_are_refused(client, cashier_headers, shift, store, manager):
    p = make_product(store, name="Bread", price="30.00", tax_rate="0")
    sale = _sell(client, cashier_headers, (p, 1))
    item_id = sale["items"][0]["id"]

    too_many = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": item_id, "qty": 2}])
    assert too_many.status_code == 400 and "only 1 can be returned" in too_many.get_json()["error"]["message"]

    half = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": item_id, "qty": "0.5"}])
    assert half.status_code == 400 and "whole units" in half.get_json()["error"]["message"]

    twice = _return(
        client, cashier_headers, sale["bill_number"],
        [{"sale_item_id": item_id, "qty": 1}, {"sale_item_id": item_id, "qty": 1}],
    )
    assert twice.status_code == 400

    other = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": 999999, "qty": 1}])
    assert other.status_code == 400


def test_weighed_item_can_be_returned_in_kg(client, cashier_headers, shift, store, manager):
    p = make_product(store, name="Tomato", price="40.00", tax_rate="0", is_variable_weight=True)
    sale = _sell(client, cashier_headers, (p, "1.5"))
    r = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": sale["items"][0]["id"], "qty": "0.5"}])
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["refund_amount"] == "20.00"


def test_manager_pin_required(client, cashier_headers, shift, store, manager):
    p = make_product(store, price="10.00", tax_rate="0")
    sale = _sell(client, cashier_headers, (p, 1))
    line = [{"sale_item_id": sale["items"][0]["id"], "qty": 1}]

    assert _return(client, cashier_headers, sale["bill_number"], line, pin="0000").status_code == 403
    own = _return(client, cashier_headers, sale["bill_number"], line, username="cashier1", pin="5678")
    assert own.status_code == 403 and "approve a return" in own.get_json()["error"]["message"]
    assert _stock(store, p) == 99  # nothing happened


def test_old_bill_is_refused(client, cashier_headers, shift, store, manager):
    p = make_product(store, price="10.00", tax_rate="0")
    sale = _sell(client, cashier_headers, (p, 1))
    row = db.session.get(Sale, sale["id"])
    row.completed_at = now_ist() - timedelta(days=31)
    db.session.commit()

    bill = _lookup(client, cashier_headers, sale["bill_number"]).get_json()
    assert bill["can_return"] is False and "31 days old" in bill["blocked_reason"]
    resp = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": sale["items"][0]["id"], "qty": 1}])
    assert resp.status_code == 400


def test_other_store_bill_is_refused(client, cashier_headers, shift, store, manager):
    other_store = make_store(name="Other Store")
    other_cashier = make_user(role="cashier", username="c2", pin="1111", store=other_store)
    make_shift(other_cashier, make_counter(other_store, code="X01"))
    token = client.post("/api/v1/auth/login", json={"username": "c2", "pin": "1111"}).get_json()["access_token"]
    other_headers = {"Authorization": f"Bearer {token}"}
    p = make_product(other_store, price="10.00", tax_rate="0")
    sale = _sell(client, other_headers, (p, 1))

    resp = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": sale["items"][0]["id"], "qty": 1}])
    assert resp.status_code == 400 and "another store" in resp.get_json()["error"]["message"]


def test_no_open_shift_is_409(client, cashier_headers, store, manager, cashier_user):
    s = make_shift(cashier_user, make_counter(store))
    p = make_product(store, price="10.00", tax_rate="0")
    sale = _sell(client, cashier_headers, (p, 1))
    client.post(f"/api/v1/shifts/{s.id}/close", json={"actual_cash": "10"}, headers=cashier_headers)
    resp = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": sale["items"][0]["id"], "qty": 1}])
    assert resp.status_code == 409


def test_restock_and_damaged(client, cashier_headers, shift, store, manager):
    good = make_product(store, name="Good", price="10.00", tax_rate="0", stock=10)
    bad = make_product(store, name="Broken", price="10.00", tax_rate="0", stock=10)
    sale = _sell(client, cashier_headers, (good, 2), (bad, 2))
    lines = {i["product_name"]: i["id"] for i in sale["items"]}

    r = _return(
        client, cashier_headers, sale["bill_number"],
        [{"sale_item_id": lines["Good"], "qty": 2}, {"sale_item_id": lines["Broken"], "qty": 1, "restock": False}],
    ).get_json()
    assert _stock(store, good) == 10  # back on the shelf
    assert _stock(store, bad) == 8  # damaged: not restocked
    txns = db.session.scalars(
        db.select(InventoryTransaction).where(InventoryTransaction.txn_type == InventoryTxnType.RETURN)
    ).all()
    assert len(txns) == 1 and txns[0].product_id == good.id and txns[0].qty == 2
    assert txns[0].reference_id == r["id"]
    assert [i["restocked"] for i in r["items"]] == [True, False]


def test_return_slip_can_be_fetched(client, cashier_headers, shift, store, manager):
    p = make_product(store, name="Milk", price="50.00", tax_rate="5.00", hsn_code="0401")
    sale = _sell(client, cashier_headers, (p, 1))
    r = _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": sale["items"][0]["id"], "qty": 1}]).get_json()

    slip = client.get(f"/api/v1/returns/{r['id']}", headers=cashier_headers).get_json()
    assert slip["bill_number"] == sale["bill_number"]
    assert slip["items"][0]["hsn_code"] == "0401"
    assert slip["gst_summary"][0]["tax"] == "2.50"
    assert slip["refund_amount"] == "52.50"


def test_shift_cash_and_reports_subtract_refunds(client, admin_headers, cashier_headers, shift, store, manager):
    p = make_product(store, name="Oil", price="100.00", tax_rate="5.00", hsn_code="1512")
    sale = _sell(client, cashier_headers, (p, 2))  # 210.00 cash
    _return(client, cashier_headers, sale["bill_number"], [{"sale_item_id": sale["items"][0]["id"], "qty": 1}])  # 105.00

    report = client.get("/api/v1/reports/sales", headers=admin_headers).get_json()
    assert report["summary"]["returns"] == 1
    assert report["summary"]["refunded"] == "105.00"
    assert report["summary"]["net_total"] == "105.00"
    assert report["gst"][0]["taxable"] == "100.00" and report["gst"][0]["tax"] == "5.00"  # net of the return
    assert report["gst_hsn"][0]["hsn_code"] == "1512" and report["gst_hsn"][0]["taxable"] == "100.00"

    shifts = client.get("/api/v1/reports/shifts", headers=admin_headers).get_json()
    assert shifts[0]["cash_refunds"] == "105.00"

    closed = client.post(f"/api/v1/shifts/{shift.id}/close", json={"actual_cash": "605"}, headers=cashier_headers)
    assert closed.get_json()["expected_cash"] == "605.00"  # 500 float + 210 sales − 105 refund
