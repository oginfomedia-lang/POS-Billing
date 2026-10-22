"""Purchase rates: the PO form starts at the supplier's last rate (never the selling price), and a goods
receipt remembers the rate paid for next time."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.supplier_product import SupplierProduct
from tests.factories import make_product, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def supplier(app):
    s = Supplier(supplier_code="SUP-RAT001", company_name="Sharma Traders", payment_terms=PaymentTerms.NET_30)
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture
def manager_headers(client, store):
    make_user(role="manager", username="mgr", pin="4321", store=store)
    token = client.post("/api/v1/auth/login", json={"username": "mgr", "pin": "4321"}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _new_product(client, headers, store, supplier, **extra):
    """Adds a product the way the Products page does, with the supplier picked from the drop-down."""
    body = {"name": "Sugar 1kg", "price": "50.00", "tax_rate": "5", "store_id": store.id,
            "supplier_id": supplier.id, **extra}
    resp = client.post("/api/v1/products", json=body, headers=headers)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _po_row(client, headers, supplier, product_id):
    rows = client.get(f"/api/v1/suppliers/{supplier.id}/po-products", headers=headers).get_json()
    return next(r for r in rows if r["id"] == product_id)


def _receive(client, headers, store, supplier, product_id, qty, price, discount="0"):
    po = client.post("/api/v1/purchases", json={
        "supplier_id": supplier.id, "store_id": store.id, "purchase_date": str(date.today()),
        "items": [{"product_id": product_id, "ordered_qty": qty, "unit_price": price, "tax_rate": "5",
                   "discount_percent": discount}],
    }, headers=headers).get_json()
    assert client.post(f"/api/v1/purchases/{po['id']}/place", headers=headers).status_code == 200
    item = {"purchase_order_item_id": po["items"][0]["id"], "qty_received": qty}
    resp = client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [item]}, headers=headers)
    assert resp.status_code == 201, resp.get_json()


def _link(supplier, product_id):
    db.session.expire_all()
    return db.session.scalar(db.select(SupplierProduct).filter_by(supplier_id=supplier.id, product_id=product_id))


def test_no_cost_means_no_rate_not_the_selling_price(client, admin_headers, store, supplier):
    p = _new_product(client, admin_headers, store, supplier)
    row = _po_row(client, admin_headers, supplier, p["id"])
    assert row["purchase_price"] is None  # was the ₹50 selling price before
    assert row["selling_price"] == 50.0


def test_rate_starts_at_the_products_cost(client, admin_headers, store, supplier):
    p = _new_product(client, admin_headers, store, supplier, cost_price="42")
    assert _po_row(client, admin_headers, supplier, p["id"])["purchase_price"] == 42.0


def test_goods_receipt_remembers_the_rate(client, admin_headers, store, supplier):
    p = _new_product(client, admin_headers, store, supplier)
    _receive(client, admin_headers, store, supplier, p["id"], 10, "45", discount="10")  # 45 − 10% = 40.50

    link = _link(supplier, p["id"])
    assert (link.purchase_price, link.last_purchase_price) == (Decimal("40.50"), None)
    assert db.session.get(Product, p["id"]).cost_price == Decimal("40.5000")  # empty default cost filled in
    assert _po_row(client, admin_headers, supplier, p["id"])["purchase_price"] == 40.5

    _receive(client, admin_headers, store, supplier, p["id"], 10, "43")
    link = _link(supplier, p["id"])
    assert (link.purchase_price, link.last_purchase_price) == (Decimal("43.00"), Decimal("40.50"))
    assert db.session.get(Product, p["id"]).cost_price == Decimal("40.5000")  # a set default cost is kept


def test_receipt_from_a_new_supplier_adds_the_product_to_their_list(client, admin_headers, store, supplier):
    p = make_product(store, name="Oil", price="150.00", stock=0)  # no supplier
    _receive(client, admin_headers, store, supplier, p.id, 5, "120")
    link = _link(supplier, p.id)
    assert link is not None and link.purchase_price == Decimal("120.00") and link.is_preferred


def test_manager_adds_product_with_cost_and_buys_it(client, manager_headers, store, supplier):
    p = _new_product(client, manager_headers, store, supplier, cost_price="41")
    assert p["cost_price"] == "41.0000"
    assert _po_row(client, manager_headers, supplier, p["id"])["purchase_price"] == 41.0
    _receive(client, manager_headers, store, supplier, p["id"], 4, "44")
    assert _po_row(client, manager_headers, supplier, p["id"])["purchase_price"] == 44.0
