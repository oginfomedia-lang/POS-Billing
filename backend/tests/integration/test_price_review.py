"""Review selling prices: which products are listed, the target % (category, parent, default), Apply / Keep as
is, the MRP limit, a new cost bringing a product back, and who may see and change prices."""
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.category import Category
from app.models.enums import PaymentTerms
from app.models.product import Product
from app.models.supplier import Supplier
from tests.factories import make_product, make_store, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def manager_headers(client, store):
    make_user(role="manager", username="mgr", pin="4321", store=store)
    token = client.post("/api/v1/auth/login", json={"username": "mgr", "pin": "4321"}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def supplier(app):
    s = Supplier(supplier_code="SUP-PRV001", company_name="Sharma Traders", payment_terms=PaymentTerms.NET_30)
    db.session.add(s)
    db.session.commit()
    return s


def _product(store, name, price, cost, tax="5", mrp=None, category=None):
    p = make_product(store, name=name, price=price, tax_rate=tax, mrp=mrp)
    p.cost_price = Decimal(cost)
    p.category_id = category.id if category else None
    db.session.commit()
    return p


def _category(name, target=None, parent=None):
    c = Category(name=name, target_margin_percent=Decimal(target) if target is not None else None,
                 parent_id=parent.id if parent else None)
    db.session.add(c)
    db.session.commit()
    return c


def _review(client, headers, **params):
    resp = client.get("/api/v1/price-review", query_string=params, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _names(client, headers, **params):
    return [r["name"] for r in _review(client, headers, **params)["items"]]


def _receive(client, headers, store, supplier, product, qty, rate):
    po = client.post("/api/v1/purchases", json={
        "supplier_id": supplier.id, "store_id": store.id, "purchase_date": str(date.today()),
        "items": [{"product_id": product.id, "ordered_qty": qty, "unit_price": rate, "tax_rate": "5"}],
    }, headers=headers).get_json()
    assert client.post(f"/api/v1/purchases/{po['id']}/place", headers=headers).status_code == 200
    item = {"purchase_order_item_id": po["items"][0]["id"], "qty_received": qty}
    assert client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [item]}, headers=headers).status_code == 201


# ── Which products are listed ────────────────────────────────────────────────

def test_lists_products_below_the_default_target(client, admin_headers, store):
    _product(store, "Sugar", price="44.00", cost="45")  # below cost
    _product(store, "Tea", price="105.00", cost="100")  # 5% < default 10%
    _product(store, "Oil", price="111.00", cost="100")  # 11%: fine
    _product(store, "Salt", price="20.00", cost="0")  # free sample: no profit asked of a ₹0 cost… still ≥ 0
    make_product(store, name="Soap", price="30.00")  # no cost: nothing to judge by

    out = _review(client, admin_headers)
    assert Decimal(out["default_margin_percent"]) == Decimal("10")
    assert [r["name"] for r in out["items"]] == ["Sugar", "Tea"]  # selling at a loss first

    sugar = out["items"][0]
    assert sugar["below_cost"] and Decimal(sugar["margin_percent"]) == Decimal("-2.22")
    assert Decimal(sugar["target_percent"]) == Decimal("10")
    assert Decimal(sugar["suggested_price"]) == Decimal("49.50")  # 45 × 1.10
    assert Decimal(sugar["suggested_price_incl"]) == Decimal("51.98")  # + 5% GST (2.475 → 2.48)
    assert Decimal(sugar["price_incl"]) == Decimal("46.20")


def test_category_target_and_parent_inheritance(client, admin_headers, store):
    grocery = _category("Grocery", target="5")
    staples = _category("Staples", parent=grocery)  # no own target: uses Grocery's 5%
    cosmetics = _category("Cosmetics", target="25")
    _product(store, "Rice", price="106.00", cost="100", category=staples)  # 6% ≥ 5%: fine
    _product(store, "Atta", price="104.00", cost="100", category=staples)  # 4% < 5%
    _product(store, "Cream", price="120.00", cost="100", category=cosmetics)  # 20% < 25%

    rows = {r["name"]: r for r in _review(client, admin_headers)["items"]}
    assert set(rows) == {"Atta", "Cream"}
    assert Decimal(rows["Atta"]["target_percent"]) == Decimal("5")
    assert Decimal(rows["Atta"]["suggested_price"]) == Decimal("105.00")
    assert Decimal(rows["Cream"]["target_percent"]) == Decimal("25")


def test_default_target_comes_from_settings(client, admin_headers, store):
    _product(store, "Tea", price="111.00", cost="100")  # 11%
    assert _names(client, admin_headers) == []
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    assert client.put("/api/v1/settings", json={**s, "default_margin_percent": "15"},
                      headers=admin_headers).status_code == 200
    assert _names(client, admin_headers) == ["Tea"]


def test_category_target_can_be_set_and_cleared_on_the_api(client, admin_headers, store):
    cat = client.post("/api/v1/categories", json={"name": "Snacks", "target_margin_percent": "18"},
                      headers=admin_headers)
    assert cat.status_code == 201 and Decimal(cat.get_json()["target_margin_percent"]) == Decimal("18")
    cid = cat.get_json()["id"]
    cleared = client.put(f"/api/v1/categories/{cid}", json={"target_margin_percent": None}, headers=admin_headers)
    assert cleared.status_code == 200 and cleared.get_json()["target_margin_percent"] is None
    bad = client.put(f"/api/v1/categories/{cid}", json={"target_margin_percent": "-5"}, headers=admin_headers)
    assert bad.status_code in (400, 422)


def test_only_some_products(client, admin_headers, store):
    a = _product(store, "Sugar", price="40.00", cost="45")
    _product(store, "Tea", price="90.00", cost="100")
    assert _names(client, admin_headers, product_ids=str(a.id)) == ["Sugar"]


# ── Apply / Keep as is ───────────────────────────────────────────────────────

def test_apply_the_suggested_price(client, admin_headers, store):
    p = _product(store, "Sugar", price="44.00", cost="45", mrp="60")
    row = _review(client, admin_headers)["items"][0]
    resp = client.post(f"/api/v1/price-review/{p.id}/apply", json={"price": row["suggested_price"]},
                       headers=admin_headers)
    assert resp.status_code == 200, resp.get_json()
    db.session.expire_all()
    assert db.session.get(Product, p.id).price == Decimal("49.50")
    assert _names(client, admin_headers) == []


def test_apply_a_typed_price_but_never_above_mrp(client, admin_headers, store):
    p = _product(store, "Biscuit", price="8.00", cost="9", tax="18", mrp="10")
    too_high = client.post(f"/api/v1/price-review/{p.id}/apply", json={"price": "8.50"}, headers=admin_headers)
    assert too_high.status_code == 400 and "MRP" in too_high.get_json()["error"]["message"]  # 8.50 + 1.53 = 10.03

    row = _review(client, admin_headers)["items"][0]
    assert row["capped_at_mrp"] and Decimal(row["suggested_price_incl"]) <= Decimal("10")
    ok = client.post(f"/api/v1/price-review/{p.id}/apply", json={"price": "8.47"}, headers=admin_headers)
    assert ok.status_code == 200  # below the target (capped), but it's what the MRP allows: not asked again
    assert _names(client, admin_headers) == []


def test_keep_as_is_until_the_cost_changes(client, admin_headers, store, supplier):
    p = _product(store, "Tea", price="105.00", cost="100")
    assert client.post(f"/api/v1/price-review/{p.id}/keep", headers=admin_headers).status_code == 200
    assert _names(client, admin_headers) == []

    _receive(client, admin_headers, store, supplier, p, 10, "102")  # new rate → new cost
    db.session.expire_all()
    assert db.session.get(Product, p.id).cost_price == Decimal("102.0000")
    assert _names(client, admin_headers) == ["Tea"]  # asked again at the new cost


def test_goods_receipt_at_a_higher_rate_lists_the_product(client, admin_headers, store, supplier):
    p = _product(store, "Sugar", price="44.00", cost="40")  # 10%: fine
    assert _names(client, admin_headers) == []
    _receive(client, admin_headers, store, supplier, p, 10, "45")
    assert _names(client, admin_headers, product_ids=str(p.id)) == ["Sugar"]


def test_price_change_is_audited(client, admin_headers, store):
    from app.models.audit_log import AuditLog
    p = _product(store, "Sugar", price="44.00", cost="45")
    client.post(f"/api/v1/price-review/{p.id}/apply", json={"price": "49.50"}, headers=admin_headers)
    log = db.session.scalar(db.select(AuditLog).where(AuditLog.action == "product.price_review"))
    assert log is not None and log.new_values["price"] == "49.50" and log.old_values["price"] == "44.00"


# ── Who ──────────────────────────────────────────────────────────────────────

def test_cashier_cannot_see_or_change(client, cashier_headers, store):
    p = _product(store, "Sugar", price="44.00", cost="45")
    assert client.get("/api/v1/price-review", headers=cashier_headers).status_code == 403
    assert client.post(f"/api/v1/price-review/{p.id}/apply", json={"price": "50"},
                       headers=cashier_headers).status_code == 403


def test_manager_sees_shared_and_own_store_products_only(client, manager_headers, store):
    _product(store, "Shared Sugar", price="44.00", cost="45")
    other = make_store(name="Other Branch")
    mine = _product(store, "Our Bread", price="20.00", cost="25")
    mine.store_id = store.id
    theirs = _product(store, "Their Bread", price="20.00", cost="25")
    theirs.store_id = other.id
    db.session.commit()

    assert set(_names(client, manager_headers)) == {"Shared Sugar", "Our Bread"}
    assert client.post(f"/api/v1/price-review/{theirs.id}/apply", json={"price": "30"},
                       headers=manager_headers).status_code == 403
    assert client.post(f"/api/v1/price-review/{mine.id}/apply", json={"price": "30"},
                       headers=manager_headers).status_code == 200
