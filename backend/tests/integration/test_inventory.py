"""Stock levels, stock-in, adjustment and ledger tests."""
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.product import Product
from tests.factories import make_product, make_store

pytestmark = pytest.mark.integration


def _levels(client, headers, store):
    resp = client.get(f"/api/v1/inventory?store_id={store.id}", headers=headers)
    assert resp.status_code == 200
    return {row["product_name"]: row for row in resp.get_json()}


def test_new_product_shows_zero_stock(client, admin_headers, store):
    db.session.add(Product(name="Unstocked", price=Decimal("5.00")))
    db.session.commit()
    row = _levels(client, admin_headers, store)["Unstocked"]
    assert row["qty_on_hand"] == "0"
    assert row["is_low"] is True


def test_stock_in_creates_row_and_ledger(client, admin_headers, store):
    product = Product(name="Rice 5kg", price=Decimal("400.00"))
    db.session.add(product)
    db.session.commit()

    for qty in ("10", "2.5"):
        resp = client.post(
            "/api/v1/inventory/stock-in",
            json={"store_id": store.id, "product_id": product.id, "qty": qty, "notes": "GRN-1"},
            headers=admin_headers,
        )
        assert resp.status_code == 200
    assert Decimal(resp.get_json()["qty_on_hand"]) == Decimal("12.5")

    ledger = client.get(f"/api/v1/inventory/ledger?store_id={store.id}&product_id={product.id}", headers=admin_headers).get_json()
    assert [(t["txn_type"], Decimal(t["qty"])) for t in ledger] == [("purchase", Decimal("2.5")), ("purchase", Decimal("10"))]


def test_adjust_sets_counted_qty(client, admin_headers, store):
    product = make_product(store, name="Soap", stock=20)
    resp = client.post(
        "/api/v1/inventory/adjust",
        json={"store_id": store.id, "product_id": product.id, "new_qty": "17", "notes": "3 damaged"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert Decimal(_levels(client, admin_headers, store)["Soap"]["qty_on_hand"]) == 17
    ledger = client.get(f"/api/v1/inventory/ledger?store_id={store.id}", headers=admin_headers).get_json()
    assert ledger[0]["txn_type"] == "adjustment"
    assert Decimal(ledger[0]["qty"]) == -3


def test_adjust_requires_reason_and_non_negative(client, admin_headers, store):
    product = make_product(store)
    base = {"store_id": store.id, "product_id": product.id}
    assert client.post("/api/v1/inventory/adjust", json={**base, "new_qty": "5"}, headers=admin_headers).status_code == 422
    assert client.post("/api/v1/inventory/adjust", json={**base, "new_qty": "-1", "notes": "x"}, headers=admin_headers).status_code == 422


def test_stock_in_rejects_product_of_other_store(client, admin_headers, store):
    other = make_store(name="Other")
    product = Product(name="Local only", price=Decimal("1.00"), store_id=other.id)
    db.session.add(product)
    db.session.commit()
    resp = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store.id, "product_id": product.id, "qty": "1"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


def test_cashier_can_read_but_not_change_stock(client, cashier_headers, store):
    product = make_product(store)
    assert client.get(f"/api/v1/inventory?store_id={store.id}", headers=cashier_headers).status_code == 200
    resp = client.post(
        "/api/v1/inventory/stock-in",
        json={"store_id": store.id, "product_id": product.id, "qty": "1"},
        headers=cashier_headers,
    )
    assert resp.status_code == 403


def test_store_id_required(client, admin_headers):
    assert client.get("/api/v1/inventory", headers=admin_headers).status_code == 422
