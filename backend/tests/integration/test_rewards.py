"""Reward points: register on first bill, earn, redeem in blocks, race on the same points, returns, receipts."""
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.customer import Customer
from app.models.enums import SaleStatus
from app.models.sale import Sale
from app.schemas.settings_schemas import SettingsData
from app.services import loyalty_service
from tests.factories import make_counter, make_product, make_shift, make_user

pytestmark = pytest.mark.integration

MOBILE = "9876543210"


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store), opening_float="500.00")


@pytest.fixture
def rewards_on(client, admin_headers):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    resp = client.put("/api/v1/settings", json={**s, "rewards_enabled": True}, headers=admin_headers)
    assert resp.status_code == 200, resp.get_json()


def _open(client, headers, *lines, mobile=MOBILE):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    for product, qty in lines:
        client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    if mobile:
        resp = client.put(f"/api/v1/sales/{sid}/customer-mobile", json={"mobile": mobile}, headers=headers)
        assert resp.status_code == 200, resp.get_json()
    return sid


def _pay(client, headers, sid):
    return client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "100000"}, headers=headers)


def _sell(client, headers, *lines, mobile=MOBILE):
    resp = _pay(client, headers, _open(client, headers, *lines, mobile=mobile))
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _redeem(client, headers, sid, blocks):
    return client.post(f"/api/v1/sales/{sid}/redeem-points", json={"blocks": blocks}, headers=headers)


def _customer() -> Customer | None:
    db.session.expire_all()
    return db.session.scalar(db.select(Customer).where(Customer.mobile == MOBILE))


def _balance(client, headers) -> dict:
    return client.get(f"/api/v1/customers/{MOBILE}/rewards", headers=headers).get_json()


def test_points_for():
    s = SettingsData()
    assert loyalty_service.points_for("99.99", s) == 0
    assert loyalty_service.points_for("1250", s) == 12
    assert loyalty_service.points_for("-5", s) == 0


def test_first_bill_registers_and_earns(client, admin_headers, cashier_headers, shift, store, rewards_on):
    p = make_product(store, price="1250.00", tax_rate="0")
    assert _balance(client, cashier_headers)["registered"] is False

    sale = _sell(client, cashier_headers, (p, 1))
    assert sale["points_earned"] == 12

    c = _customer()
    assert (c.points_balance, c.visit_count, c.total_spent, c.lifetime_earned) == (12, 1, Decimal("1250.00"), 12)
    info = _balance(client, cashier_headers)
    assert (info["registered"], info["points_balance"], info["max_blocks"]) == (True, 12, 0)

    page = client.get("/api/v1/customers", headers=admin_headers).get_json()
    assert page["total"] == 1 and page["items"][0]["mobile"] == MOBILE
    txns = client.get(f"/api/v1/customers/{c.id}/transactions", headers=admin_headers).get_json()["items"]
    assert [(t["txn_type"], t["points"], t["balance_after"]) for t in txns] == [("earn", 12, 12)]


def test_no_mobile_no_customer(client, cashier_headers, shift, store, rewards_on):
    _sell(client, cashier_headers, (make_product(store, price="500.00", tax_rate="0"), 1), mobile=None)
    assert db.session.scalar(db.select(db.func.count(Customer.id))) == 0


def test_rewards_off_registers_but_gives_no_points(client, cashier_headers, shift, store):
    sale = _sell(client, cashier_headers, (make_product(store, price="500.00", tax_rate="0"), 1))
    assert sale["points_earned"] == 0 and _customer().points_balance == 0


def test_redeem_block_before_gst_then_settle(client, cashier_headers, shift, store, rewards_on):
    big = make_product(store, price="25000.00", tax_rate="0")
    _sell(client, cashier_headers, (big, 1))  # 250 points
    assert _customer().points_balance == 250

    p = make_product(store, price="800.00", tax_rate="5.00")  # ₹840 with GST
    sid = _open(client, cashier_headers, (p, 1))
    resp = _redeem(client, cashier_headers, sid, 2)
    assert resp.status_code == 200, resp.get_json()
    s = resp.get_json()
    # ₹200 off before GST: 600 + 30 GST = 630
    assert (s["points_redeemed"], s["reward_discount"], s["tax_amount"], s["total"]) == (200, "200.00", "30.00", "630.00")
    assert s["items"][0]["reward_discount"] == "200.00" and s["items"][0]["discount_amount"] == "200.00"
    assert _customer().points_balance == 250  # only reserved so far

    paid = _pay(client, cashier_headers, sid).get_json()
    assert paid["points_earned"] == 6  # on the ₹630 actually paid
    c = _customer()
    assert (c.points_balance, c.lifetime_redeemed) == (250 - 200 + 6, 200)

    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert (receipt["points_redeemed"], receipt["reward_discount"], receipt["points_earned"], receipt["points_balance"]) == (
        200, "200.00", 6, 56
    )


def test_redeem_checks(client, cashier_headers, shift, store, rewards_on):
    _sell(client, cashier_headers, (make_product(store, price="15000.00", tax_rate="0"), 1))  # 150 points
    sid = _open(client, cashier_headers, (make_product(store, price="500.00", tax_rate="0"), 1))

    assert _redeem(client, cashier_headers, sid, 2).status_code == 400  # only 150 points
    assert _redeem(client, cashier_headers, sid, 1).get_json()["total"] == "400.00"
    removed = _redeem(client, cashier_headers, sid, 0).get_json()
    assert (removed["points_redeemed"], removed["total"]) == (0, "500.00")


def test_redeem_needs_mobile_and_big_enough_bill(client, cashier_headers, shift, store, rewards_on):
    _sell(client, cashier_headers, (make_product(store, price="15000.00", tax_rate="0"), 1))
    sid = _open(client, cashier_headers, (make_product(store, price="50.00", tax_rate="0"), 1), mobile=None)
    assert "mobile" in _redeem(client, cashier_headers, sid, 1).get_json()["error"]["message"]
    client.put(f"/api/v1/sales/{sid}/customer-mobile", json={"mobile": MOBILE}, headers=cashier_headers)
    assert "too small" in _redeem(client, cashier_headers, sid, 1).get_json()["error"]["message"]


def test_removing_items_lowers_redemption_and_mobile_change_drops_it(client, cashier_headers, shift, store, rewards_on):
    _sell(client, cashier_headers, (make_product(store, price="30000.00", tax_rate="0"), 1))  # 300 points
    a = make_product(store, name="A", price="150.00", tax_rate="0")
    b = make_product(store, name="B", price="100.00", tax_rate="0")
    sid = _open(client, cashier_headers, (a, 1), (b, 1))
    redeemed = _redeem(client, cashier_headers, sid, 2).get_json()
    assert redeemed["total"] == "50.00"

    item_a = next(i for i in redeemed["items"] if i["product_name"] == "A")
    s = client.delete(f"/api/v1/sales/{sid}/items/{item_a['id']}", headers=cashier_headers).get_json()
    assert (s["points_redeemed"], s["total"]) == (100, "0.00")  # ₹100 bill takes one block only

    s = client.put(f"/api/v1/sales/{sid}/customer-mobile", json={"mobile": "9123456789"}, headers=cashier_headers).get_json()
    assert (s["points_redeemed"], s["total"]) == (0, "100.00")


def test_same_points_cannot_be_spent_twice(client, cashier_headers, shift, store, rewards_on):
    _sell(client, cashier_headers, (make_product(store, price="10000.00", tax_rate="0"), 1))  # 100 points
    p = make_product(store, price="500.00", tax_rate="0")

    cashier2 = make_user(role="cashier", username="cashier2", pin="2468", store=store)
    make_shift(cashier2, make_counter(store, code="C02", label="Counter 2"))
    token = client.post("/api/v1/auth/login", json={"username": "cashier2", "pin": "2468"}).get_json()["access_token"]
    h2 = {"Authorization": f"Bearer {token}"}

    s1 = _open(client, cashier_headers, (p, 1))
    s2 = _open(client, h2, (p, 1))
    assert _redeem(client, cashier_headers, s1, 1).status_code == 200
    assert _redeem(client, h2, s2, 1).status_code == 200  # both reserved: the balance is checked again on payment

    assert _pay(client, cashier_headers, s1).status_code == 200
    resp = _pay(client, h2, s2)
    assert resp.status_code == 409 and "only 4 points" in resp.get_json()["error"]["message"]
    db.session.expire_all()
    sale2 = db.session.get(Sale, s2)
    assert sale2.status is SaleStatus.OPEN and sale2.bill_number is None  # whole sale rolled back
    assert _customer().points_balance == 4  # 100 - 100 + 4 earned on ₹400


def test_returns_take_back_earned_points(client, cashier_headers, shift, store, rewards_on):
    make_user(role="manager", username="mgr", pin="4321", store=store)
    p = make_product(store, price="100.00", tax_rate="0")
    sale = _sell(client, cashier_headers, (p, 10))  # ₹1000 -> 10 points
    item_id = sale["items"][0]["id"]

    def ret(qty):
        resp = client.post("/api/v1/returns", json={
            "bill_number": sale["bill_number"], "lines": [{"sale_item_id": item_id, "qty": qty}],
            "reason": "Damaged", "approver_username": "mgr", "approver_pin": "4321",
        }, headers=cashier_headers)
        assert resp.status_code == 201, resp.get_json()

    ret(3)  # ₹300 refunded -> 3 points back
    assert _customer().points_balance == 7
    ret(4)  # ₹700 refunded in all -> 7 back in all
    assert _customer().points_balance == 3
    ret(3)  # everything returned
    c = _customer()
    assert (c.points_balance, c.lifetime_earned) == (0, 0)
    txns = client.get(f"/api/v1/customers/{c.id}/transactions", headers=cashier_headers)
    assert txns.status_code == 403  # passbook is for admins/managers


def test_redeem_rejected_when_switched_off(client, admin_headers, cashier_headers, shift, store, rewards_on):
    _sell(client, cashier_headers, (make_product(store, price="10000.00", tax_rate="0"), 1))
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    client.put("/api/v1/settings", json={**s, "rewards_enabled": False}, headers=admin_headers)
    sid = _open(client, cashier_headers, (make_product(store, price="500.00", tax_rate="0"), 1))
    assert "switched off" in _redeem(client, cashier_headers, sid, 1).get_json()["error"]["message"]
    assert _balance(client, cashier_headers)["max_blocks"] == 0
