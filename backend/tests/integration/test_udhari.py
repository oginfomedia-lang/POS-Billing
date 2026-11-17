"""Customer udhari (khata): credit sales, the credit limit, repayments (and the cash they put in the drawer),
returns from an udhari bill, and how all of it reaches the Tally vouchers."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.customer import Customer
from tests.factories import make_counter, make_product, make_shift, make_store, make_user

pytestmark = pytest.mark.integration

MOBILE = "9876543210"
TODAY = str(date.today())


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store), opening_float="0.00")


@pytest.fixture
def manager(store):
    return make_user(role="manager", username="mgr", pin="4321", store=store)


@pytest.fixture
def product(store):
    return make_product(store, name="Sugar 1kg", price="50.00", tax_rate="5.00")


def _cart(client, headers, product, qty=1, mobile=MOBILE):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    resp = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    assert resp.status_code in (200, 201), resp.get_json()
    if mobile:
        assert client.put(f"/api/v1/sales/{sid}/customer-mobile", json={"mobile": mobile},
                          headers=headers).status_code == 200
    return sid


def _complete(client, headers, sid, method="credit"):
    body = {"method": method}
    if method == "cash":
        body["cash_tendered"] = "10000"
    return client.post(f"/api/v1/sales/{sid}/complete", json=body, headers=headers)


def _credit_sale(client, headers, product, qty=1):
    resp = _complete(client, headers, _cart(client, headers, product, qty))
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _customer() -> Customer:
    db.session.expire_all()
    return db.session.scalar(db.select(Customer).where(Customer.mobile == MOBILE))


def _passbook(client, headers, customer_id):
    resp = client.get(f"/api/v1/customers/{customer_id}/credit-transactions", headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["items"]


def _repay(client, headers, customer_id, amount, method="cash", **extra):
    return client.post(f"/api/v1/customers/{customer_id}/repay",
                       json={"amount": amount, "payment_method": method, **extra}, headers=headers)


def _drawer(client, headers, shift):
    resp = client.get(f"/api/v1/shifts/{shift.id}/bills", headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["summary"]


def _return_all(client, headers, bill):
    found = client.get(f"/api/v1/returns/bill/{bill['bill_number']}", headers=headers).get_json()
    lines = [{"sale_item_id": ln["sale_item_id"], "qty": str(ln["qty_returnable"]), "restock": True}
             for ln in found["lines"]]
    return client.post("/api/v1/returns", json={
        "bill_number": bill["bill_number"], "lines": lines, "reason": "Changed mind",
        "approver_username": "mgr", "approver_pin": "4321",
    }, headers=headers)


def _daybook(client, headers):
    resp = client.get("/api/v1/accounting/daybook", query_string={"date_from": TODAY, "date_to": TODAY},
                      headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _ledgers(voucher):
    return {ln["ledger"]: (Decimal(ln["debit"]), Decimal(ln["credit"])) for ln in voucher["lines"]}


# ── Credit sales ─────────────────────────────────────────────────────────────

def test_credit_sale_goes_on_the_khata_not_in_the_drawer(client, cashier_headers, admin_headers, shift, product):
    bill = _credit_sale(client, cashier_headers, product, qty=2)
    total = Decimal(bill["total"])

    customer = _customer()
    assert customer.credit_balance == total
    [entry] = _passbook(client, admin_headers, customer.id)
    assert entry["txn_type"] == "udhari" and Decimal(entry["amount"]) == total
    assert Decimal(entry["balance_after"]) == total

    summary = _drawer(client, cashier_headers, shift)
    assert Decimal(summary["credit_sales"]) == total
    assert Decimal(summary["expected_cash"]) == 0  # nothing came into the drawer


def test_credit_sale_needs_a_mobile(client, cashier_headers, shift, product):
    sid = _cart(client, cashier_headers, product, mobile=None)
    resp = _complete(client, cashier_headers, sid)
    assert resp.status_code == 400 and "mobile" in resp.get_json()["error"]["message"]


def test_credit_limit_stops_the_bill(client, cashier_headers, admin_headers, shift, product):
    first = _credit_sale(client, cashier_headers, product)
    customer = _customer()
    limit = client.put(f"/api/v1/customers/{customer.id}/credit-limit",
                       json={"credit_limit": first["total"]}, headers=admin_headers)
    assert limit.status_code == 200, limit.get_json()

    resp = _complete(client, cashier_headers, _cart(client, cashier_headers, product))
    assert resp.status_code == 400 and "limit" in resp.get_json()["error"]["message"].lower()
    assert _customer().credit_balance == Decimal(first["total"])  # the refused bill left no trace


# ── Repayments ───────────────────────────────────────────────────────────────

def test_cash_repayment_at_the_counter_goes_in_that_drawer(client, cashier_headers, shift, product):
    bill = _credit_sale(client, cashier_headers, product, qty=2)
    customer = _customer()

    resp = _repay(client, cashier_headers, customer.id, "40.00")
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["shift_id"] == shift.id
    assert _customer().credit_balance == Decimal(bill["total"]) - Decimal("40.00")

    summary = _drawer(client, cashier_headers, shift)
    assert Decimal(summary["udhari_cash"]) == Decimal("40.00")
    assert Decimal(summary["expected_cash"]) == Decimal("40.00")


def test_upi_repayment_does_not_touch_the_drawer(client, cashier_headers, shift, product):
    _credit_sale(client, cashier_headers, product)
    resp = _repay(client, cashier_headers, _customer().id, "10.00", method="upi", reference="UTR1")
    assert resp.status_code == 201 and resp.get_json()["shift_id"] is None
    assert Decimal(_drawer(client, cashier_headers, shift)["expected_cash"]) == 0


def test_cannot_pay_more_than_is_owed(client, cashier_headers, shift, product):
    bill = _credit_sale(client, cashier_headers, product)
    customer = _customer()

    too_much = _repay(client, cashier_headers, customer.id, str(Decimal(bill["total"]) + 1))
    assert too_much.status_code == 400 and "only" in too_much.get_json()["error"]["message"]

    assert _repay(client, cashier_headers, customer.id, bill["total"]).status_code == 201
    nothing_due = _repay(client, cashier_headers, customer.id, "1.00")
    assert nothing_due.status_code == 400 and "no udhari dues" in nothing_due.get_json()["error"]["message"]
    assert _customer().credit_balance == 0


def test_repayment_is_recorded_at_the_staff_members_own_store(client, cashier_headers, shift, product, store):
    _credit_sale(client, cashier_headers, product)
    other = make_store(name="Other Store")
    resp = _repay(client, cashier_headers, _customer().id, "5.00", store_id=other.id)  # ignored: not head office
    assert resp.status_code == 201
    [payment] = [t for t in _passbook_rows() if t.txn_type.value == "payment"]
    assert payment.store_id == store.id


def _passbook_rows():
    from app.models.customer import CreditTransaction
    db.session.expire_all()
    return db.session.scalars(db.select(CreditTransaction).order_by(CreditTransaction.id)).all()


# ── Returns from an udhari bill ──────────────────────────────────────────────

def test_return_from_udhari_bill_comes_off_the_khata(client, cashier_headers, admin_headers, shift, product, manager):
    bill = _credit_sale(client, cashier_headers, product, qty=2)
    customer = _customer()

    # The drawer is empty (float 0, no cash sales); a cash refund would be refused. This one needs no cash.
    resp = _return_all(client, cashier_headers, bill)
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["refund_method"] == "credit"

    assert _customer().credit_balance == 0
    entries = _passbook(client, admin_headers, customer.id)
    assert [e["txn_type"] for e in entries] == ["return", "udhari"]  # newest first
    assert Decimal(entries[0]["amount"]) == -Decimal(bill["total"])
    assert entries[0]["return_id"] == resp.get_json()["id"]

    summary = _drawer(client, cashier_headers, shift)
    assert Decimal(summary["cash_refunds"]) == 0 and Decimal(summary["expected_cash"]) == 0


def test_return_after_dues_were_paid_leaves_money_with_the_store(client, cashier_headers, shift, product, manager):
    bill = _credit_sale(client, cashier_headers, product)
    customer = _customer()
    assert _repay(client, cashier_headers, customer.id, bill["total"]).status_code == 201

    assert _return_all(client, cashier_headers, bill).status_code == 201
    assert _customer().credit_balance == -Decimal(bill["total"])  # the store holds it for the next udhari bill

    _credit_sale(client, cashier_headers, product)  # it is used up by the next bill
    assert _customer().credit_balance == 0


def test_cash_bill_return_is_still_paid_in_cash(client, cashier_headers, shift, product, manager):
    resp = _complete(client, cashier_headers, _cart(client, cashier_headers, product), method="cash")
    ret = _return_all(client, cashier_headers, resp.get_json())
    assert ret.status_code == 201 and ret.get_json()["refund_method"] == "cash"


# ── Accounting (Tally) ───────────────────────────────────────────────────────

def test_udhari_in_the_day_book(client, cashier_headers, admin_headers, shift, product, manager):
    bill = _credit_sale(client, cashier_headers, product, qty=2)
    total = Decimal(bill["total"])
    customer = _customer()
    assert _repay(client, cashier_headers, customer.id, "30.00").status_code == 201
    assert _repay(client, cashier_headers, customer.id, "20.00", method="upi", reference="UTR9").status_code == 201

    book = _daybook(client, admin_headers)
    assert book["warnings"] == []
    by_type = {}
    for v in book["vouchers"]:
        by_type.setdefault(v["voucher_type"], []).append(v)

    [sales] = by_type["sales"]
    lines = _ledgers(sales)
    assert lines["Udhari Customers"] == (total, Decimal("0"))  # owed, not cash
    assert "Cash" not in lines

    receipts = {v["number"]: _ledgers(v) for v in by_type["receipt"]}
    assert len(receipts) == 2
    cash_receipt, upi_receipt = (receipts[k] for k in sorted(receipts))
    assert cash_receipt == {"Cash": (Decimal("30.00"), Decimal("0")), "Udhari Customers": (Decimal("0"), Decimal("30.00"))}
    assert upi_receipt == {"Bank Account": (Decimal("20.00"), Decimal("0")),
                           "Udhari Customers": (Decimal("0"), Decimal("20.00"))}


def test_udhari_return_credits_the_udhari_ledger(client, cashier_headers, admin_headers, shift, product, manager):
    bill = _credit_sale(client, cashier_headers, product)
    assert _return_all(client, cashier_headers, bill).status_code == 201

    [note] = [v for v in _daybook(client, admin_headers)["vouchers"] if v["voucher_type"] == "credit_note"]
    lines = _ledgers(note)
    assert lines["Udhari Customers"] == (Decimal("0"), Decimal(bill["total"]))
    assert "Cash" not in lines


def test_udhari_ledger_is_a_sundry_debtor_in_the_tally_file(client, cashier_headers, admin_headers, shift, product):
    import xml.etree.ElementTree as ET

    _credit_sale(client, cashier_headers, product)
    resp = client.get("/api/v1/accounting/tally-export",
                      query_string={"date_from": TODAY, "date_to": TODAY, "what": "ledgers"}, headers=admin_headers)
    assert resp.status_code == 200
    groups = {led.get("NAME"): led.findtext("PARENT") for led in ET.fromstring(resp.data).iter("LEDGER")}
    assert groups["Udhari Customers"] == "Sundry Debtors"
