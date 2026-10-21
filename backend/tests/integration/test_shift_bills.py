"""GET /shifts/<id>/bills: the cashier's bills on one shift, refunds, and the cash the drawer should hold."""
import pytest

from tests.factories import make_counter, make_product, make_shift, make_store, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store), opening_float="500.00")


@pytest.fixture
def manager(store):
    return make_user(role="manager", username="mgr", pin="4321", store=store)


def _login(client, username, pin):
    token = client.post("/api/v1/auth/login", json={"username": username, "pin": pin}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _draft(client, headers, product, qty=1):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    return sid


def _sell(client, headers, product, qty=1, method="cash", **extra):
    sid = _draft(client, headers, product, qty)
    body = {"method": method, **({"cash_tendered": "10000"} if method == "cash" else {}), **extra}
    resp = client.post(f"/api/v1/sales/{sid}/complete", json=body, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _manual_card_upi(client, admin_headers):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    client.put("/api/v1/settings", json={**s, "card_upi_mode": "manual"}, headers=admin_headers)


def _bills(client, headers, shift_id):
    return client.get(f"/api/v1/shifts/{shift_id}/bills", headers=headers)


def test_empty_shift(client, cashier_headers, shift):
    resp = _bills(client, cashier_headers, shift.id)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["bills"] == [] and data["returns"] == []
    assert data["summary"]["paid_bills"] == 0
    assert data["summary"]["sales_total"] == "0.00"
    assert data["summary"]["expected_cash"] == "500.00"  # just the opening float


def test_cash_card_upi_and_refund_are_split(client, admin_headers, cashier_headers, shift, store, manager):
    _manual_card_upi(client, admin_headers)
    p = make_product(store, name="Oil", price="100.00", tax_rate="0.00")
    cash_bill = _sell(client, cashier_headers, p, qty=2)  # 200 cash
    _sell(client, cashier_headers, p, method="card", reference="SLIP1")  # 100 card
    _sell(client, cashier_headers, p, qty=3, method="upi", reference="UTR1")  # 300 UPI
    ret = client.post("/api/v1/returns", json={
        "bill_number": cash_bill["bill_number"],
        "lines": [{"sale_item_id": cash_bill["items"][0]["id"], "qty": 1}],
        "reason": "Damaged", "approver_username": "mgr", "approver_pin": "4321",
    }, headers=cashier_headers)
    assert ret.status_code == 201, ret.get_json()

    data = _bills(client, cashier_headers, shift.id).get_json()
    s = data["summary"]
    assert s["paid_bills"] == 3
    assert (s["sales_total"], s["cash_sales"], s["card_sales"], s["upi_sales"]) == ("600.00", "200.00", "100.00", "300.00")
    assert (s["returns"], s["cash_refunds"]) == (1, "100.00")
    assert s["expected_cash"] == "600.00"  # 500 float + 200 cash − 100 refund; card / UPI not in the drawer

    first = next(b for b in data["bills"] if b["bill_number"] == cash_bill["bill_number"])
    assert first["payments"] == [{"method": "cash", "amount": "200.00"}]
    assert (first["return_count"], first["refunded"]) == (1, "100.00")
    assert data["returns"][0]["bill_number"] == cash_bill["bill_number"]

    # Closing the shift uses the same figure.
    closed = client.post(f"/api/v1/shifts/{shift.id}/close", json={"actual_cash": "590"}, headers=cashier_headers)
    assert closed.get_json()["expected_cash"] == s["expected_cash"]
    assert _bills(client, cashier_headers, shift.id).get_json()["summary"]["expected_cash"] == "600.00"


def test_held_and_voided_bills_are_listed_but_not_counted(client, cashier_headers, shift, store):
    p = make_product(store, price="50.00", tax_rate="0.00")
    _sell(client, cashier_headers, p)
    held = _draft(client, cashier_headers, p)
    client.post(f"/api/v1/sales/{held}/hold", json={}, headers=cashier_headers)
    voided = _draft(client, cashier_headers, p)
    client.post(f"/api/v1/sales/{voided}/void", headers=cashier_headers)
    empty = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]  # empty draft: not listed

    data = _bills(client, cashier_headers, shift.id).get_json()
    statuses = {b["id"]: b["status"] for b in data["bills"]}
    assert statuses[held] == "held" and statuses[voided] == "voided" and empty not in statuses
    s = data["summary"]
    assert (s["paid_bills"], s["held_bills"], s["voided_bills"]) == (1, 1, 1)
    assert s["sales_total"] == "50.00" and s["expected_cash"] == "550.00"


def test_only_this_shifts_bills(client, cashier_headers, cashier_user, shift, store):
    p = make_product(store, price="10.00", tax_rate="0.00")
    first = _sell(client, cashier_headers, p)
    client.post(f"/api/v1/shifts/{shift.id}/close", json={"actual_cash": "510"}, headers=cashier_headers)
    second_shift = make_shift(cashier_user, make_counter(store, code="C02"))
    second = _sell(client, cashier_headers, p, qty=2)

    old = [b["id"] for b in _bills(client, cashier_headers, shift.id).get_json()["bills"]]
    new = [b["id"] for b in _bills(client, cashier_headers, second_shift.id).get_json()["bills"]]
    assert old == [first["id"]] and new == [second["id"]]


def test_other_cashier_cannot_see_the_shift(client, cashier_headers, shift, store, manager, admin_headers):
    make_user(role="cashier", username="other", pin="9999", store=store)
    other = _login(client, "other", "9999")
    assert _bills(client, other, shift.id).status_code == 404
    assert _bills(client, cashier_headers, 999999).status_code == 404

    # Admin and the store's manager may look; a manager of another store may not.
    assert _bills(client, admin_headers, shift.id).status_code == 200
    assert _bills(client, _login(client, "mgr", "4321"), shift.id).status_code == 200
    make_user(role="manager", username="mgr2", pin="4321", store=make_store(name="Branch 2"))
    assert _bills(client, _login(client, "mgr2", "4321"), shift.id).status_code == 404


def test_needs_login(client, shift):
    assert _bills(client, {}, shift.id).status_code == 401


def test_shift_cannot_close_with_a_held_or_unfinished_bill(client, cashier_headers, shift, store):
    p = make_product(store, price="10.00", tax_rate="0.00")
    held = _draft(client, cashier_headers, p)
    client.post(f"/api/v1/sales/{held}/hold", json={"note": "wallet"}, headers=cashier_headers)

    def close():
        return client.post(f"/api/v1/shifts/{shift.id}/close", json={"actual_cash": "500"}, headers=cashier_headers)

    resp = close()
    assert resp.status_code == 409
    assert "1 bill is on hold" in resp.get_json()["error"]["message"]
    assert resp.get_json()["error"]["details"] == {"held_bills": 1, "open_bills": 0}

    # Resumed but not paid: still unfinished.
    client.post(f"/api/v1/sales/{held}/resume", headers=cashier_headers)
    assert "current bill has items" in close().get_json()["error"]["message"]

    # Paid: the shift closes. (An empty bill left ready on the till doesn't block it.)
    client.post(f"/api/v1/sales/{held}/complete", json={"method": "cash", "cash_tendered": "10"}, headers=cashier_headers)
    client.post("/api/v1/sales", headers=cashier_headers)
    assert close().status_code == 200


def test_voided_held_bill_no_longer_blocks_closing(client, cashier_headers, shift, store):
    p = make_product(store, price="10.00", tax_rate="0.00")
    held = _draft(client, cashier_headers, p)
    client.post(f"/api/v1/sales/{held}/hold", json={}, headers=cashier_headers)
    client.post(f"/api/v1/sales/{held}/resume", headers=cashier_headers)
    client.post(f"/api/v1/sales/{held}/void", headers=cashier_headers)
    assert client.post(f"/api/v1/shifts/{shift.id}/close", json={"actual_cash": "500"},
                       headers=cashier_headers).status_code == 200
