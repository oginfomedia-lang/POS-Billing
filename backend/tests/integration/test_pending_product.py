"""A product typed on a purchase order before the supplier's bill: no selling price, so billing refuses it; the
goods receipt takes the bill's rate / GST / MRP / HSN (correcting the PO line); Selling prices sets the price."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.product import Product
from app.models.purchase import PurchaseOrder, PurchaseOrderItem
from app.models.supplier import Supplier
from tests.factories import make_counter, make_product, make_shift, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def supplier(app):
    s = Supplier(supplier_code="SUP-PND001", company_name="Sharma Traders", payment_terms=PaymentTerms.NET_30)
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture
def manager_headers(client, store):
    make_user(role="manager", username="mgr", pin="4321", store=store)
    token = client.post("/api/v1/auth/login", json={"username": "mgr", "pin": "4321"}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _pending(client, headers, supplier, name="Test Sugar", **extra):
    resp = client.post("/api/v1/products/pending",
                       json={"name": name, "uom": "kg", "supplier_id": supplier.id, **extra}, headers=headers)
    return resp


def _order(client, headers, store, supplier, product_id, qty, rate, tax="0"):
    po = client.post("/api/v1/purchases", json={
        "supplier_id": supplier.id, "store_id": store.id, "purchase_date": str(date.today()),
        "items": [{"product_id": product_id, "ordered_qty": qty, "unit_price": rate, "tax_rate": tax}],
    }, headers=headers)
    assert po.status_code == 201, po.get_json()
    po = po.get_json()
    assert client.post(f"/api/v1/purchases/{po['id']}/place", headers=headers).status_code == 200
    return po


def _receive(client, headers, po, qty, **bill):
    item = {"purchase_order_item_id": po["items"][0]["id"], "qty_received": qty, **bill}
    return client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [item]}, headers=headers)


def _bill_item(client, headers, product_id):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    return client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product_id, "qty": 1}, headers=headers)


def _review(client, headers):
    resp = client.get("/api/v1/price-review", headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return {r["name"]: r for r in resp.get_json()["items"]}


def _product(pid) -> Product:
    db.session.expire_all()
    return db.session.get(Product, pid)


# ── Creating it ──────────────────────────────────────────────────────────────

def test_create_pending_product(client, admin_headers, supplier):
    resp = _pending(client, admin_headers, supplier)
    assert resp.status_code == 201, resp.get_json()
    p = resp.get_json()
    assert p["details_pending"] is True and Decimal(p["price"]) == 0 and p["sku"]
    assert p["uom"] == "kg" and p["supplier_id"] == supplier.id


def test_same_name_is_refused(client, admin_headers, supplier):
    assert _pending(client, admin_headers, supplier).status_code == 201
    again = _pending(client, admin_headers, supplier, name="test SUGAR")
    assert again.status_code == 409 and "already exists" in again.get_json()["error"]["message"]


def test_manager_may_add_cashier_may_not(client, manager_headers, cashier_headers, supplier):
    assert _pending(client, manager_headers, supplier).status_code == 201
    assert _pending(client, cashier_headers, supplier, name="Other").status_code == 403


# ── Billing refuses it ───────────────────────────────────────────────────────

def test_billing_refuses_a_product_without_a_price(client, admin_headers, cashier_headers, supplier, shift):
    pid = _pending(client, admin_headers, supplier).get_json()["id"]
    resp = _bill_item(client, cashier_headers, pid)
    assert resp.status_code == 400 and "selling price" in resp.get_json()["error"]["message"]


def test_not_in_the_offline_catalogue(client, admin_headers, cashier_headers, supplier, store, shift):
    pid = _pending(client, admin_headers, supplier).get_json()["id"]
    body = client.get("/api/v1/pos/offline-catalog", query_string={"store_id": store.id},
                      headers=cashier_headers).get_json()
    assert pid not in {p["id"] for p in body["products"]}


# ── Goods receipt with the bill's details ────────────────────────────────────

def test_receipt_takes_the_bill_details(client, admin_headers, supplier, store):
    pid = _pending(client, admin_headers, supplier).get_json()["id"]
    po = _order(client, admin_headers, store, supplier, pid, 10, "40")
    assert po["items"][0]["product_details_pending"] is True

    resp = _receive(client, admin_headers, po, 10, bill_unit_price="42", bill_tax_rate="5", mrp="60", hsn_code="1701")
    assert resp.status_code == 201, resp.get_json()

    db.session.expire_all()
    line = db.session.get(PurchaseOrderItem, po["items"][0]["id"])
    assert (line.unit_price, line.tax_rate) == (Decimal("42.00"), Decimal("5.00"))
    assert (line.line_total, line.tax_amount) == (Decimal("420.00"), Decimal("21.00"))
    assert db.session.get(PurchaseOrder, po["id"]).grand_total == Decimal("441.00")  # the PO follows the bill

    p = _product(pid)
    assert (p.mrp, p.hsn_code, p.tax_rate) == (Decimal("60.00"), "1701", Decimal("5.00"))
    assert p.cost_price == Decimal("42.0000")  # the cost is the billed rate
    assert p.details_pending  # still no selling price

    from app.models.audit_log import AuditLog
    log = db.session.scalar(db.select(AuditLog).where(AuditLog.action == "purchase.rate_from_bill"))
    assert log is not None and log.new_values["lines"][0]["new"]["unit_price"] == "42.00"


def test_rate_is_locked_once_part_of_the_line_came_in(client, admin_headers, supplier, store):
    p = make_product(store, name="Oil", price="150.00", stock=0)
    po = _order(client, admin_headers, store, supplier, p.id, 10, "100", tax="5")
    assert _receive(client, admin_headers, po, 4).status_code == 201
    resp = _receive(client, admin_headers, po, 6, bill_unit_price="105")
    assert resp.status_code == 422 and "can't change now" in resp.get_json()["error"]["message"]
    assert _receive(client, admin_headers, po, 6, bill_unit_price="100").status_code == 201  # same rate: fine


def test_existing_product_keeps_its_selling_gst(client, admin_headers, supplier, store):
    p = make_product(store, name="Biscuit", price="20.00", tax_rate="12", stock=0)
    po = _order(client, admin_headers, store, supplier, p.id, 10, "15", tax="12")
    assert _receive(client, admin_headers, po, 10, bill_tax_rate="5").status_code == 201
    db.session.expire_all()
    assert db.session.get(PurchaseOrderItem, po["items"][0]["id"]).tax_rate == Decimal("5.00")  # bought at 5%
    assert _product(p.id).tax_rate == Decimal("12.00")  # sold as before


def test_unchanged_bill_leaves_the_po_alone(client, admin_headers, supplier, store):
    from app.models.audit_log import AuditLog
    p = make_product(store, name="Tea", price="120.00", stock=0)
    po = _order(client, admin_headers, store, supplier, p.id, 5, "100", tax="5")
    assert _receive(client, admin_headers, po, 5, bill_unit_price="100", bill_tax_rate="5").status_code == 201
    assert db.session.scalar(db.select(AuditLog).where(AuditLog.action == "purchase.rate_from_bill")) is None


# ── Selling prices ───────────────────────────────────────────────────────────

def test_review_lists_it_and_apply_makes_it_sellable(client, admin_headers, cashier_headers, supplier, store, shift):
    pid = _pending(client, admin_headers, supplier).get_json()["id"]
    po = _order(client, admin_headers, store, supplier, pid, 10, "40")
    _receive(client, admin_headers, po, 10, bill_tax_rate="5", mrp="60")

    row = _review(client, admin_headers)["Test Sugar"]
    assert row["details_pending"] and Decimal(row["suggested_price"]) == Decimal("44.00")  # 40 + default 10%

    assert client.post(f"/api/v1/price-review/{pid}/keep", headers=admin_headers).status_code == 400
    assert client.post(f"/api/v1/price-review/{pid}/apply", json={"price": row["suggested_price"]},
                       headers=admin_headers).status_code == 200
    assert not _product(pid).details_pending
    assert _bill_item(client, cashier_headers, pid).status_code in (200, 201)


def test_lower_mrp_on_new_stock_is_flagged(client, admin_headers, supplier, store):
    p = make_product(store, name="Shampoo", price="47.62", tax_rate="5", mrp="60", stock=0)  # 50.00 with GST
    p.cost_price = Decimal("40")
    p.price_reviewed_cost = Decimal("40")  # price already reviewed at this cost
    db.session.commit()
    po = _order(client, admin_headers, store, supplier, p.id, 5, "40", tax="5")
    assert _receive(client, admin_headers, po, 5, mrp="48").status_code == 201  # new stock printed ₹48

    row = _review(client, admin_headers)["Shampoo"]
    assert row["above_mrp"] and Decimal(row["suggested_price_incl"]) <= Decimal("48")
    assert client.post(f"/api/v1/price-review/{p.id}/keep", headers=admin_headers).status_code == 400


def test_products_page_price_ends_pending_only_when_above_zero(client, admin_headers, supplier):
    pid = _pending(client, admin_headers, supplier).get_json()["id"]
    assert client.put(f"/api/v1/products/{pid}", json={"name": "Test Sugar 1kg", "price": "0"},
                      headers=admin_headers).status_code == 200
    assert _product(pid).details_pending
    assert client.put(f"/api/v1/products/{pid}", json={"price": "45"}, headers=admin_headers).status_code == 200
    assert not _product(pid).details_pending
