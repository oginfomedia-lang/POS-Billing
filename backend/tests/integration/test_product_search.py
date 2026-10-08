"""Billing-screen suggestions: a cashier searches active products by name / SKU / barcode."""
import pytest

from app.extensions import db
from tests.factories import make_product

pytestmark = pytest.mark.integration


def _search(client, headers, text, **params):
    resp = client.get("/api/v1/products", query_string={"q": text, "active_only": "true", "per_page": 8, **params}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return [p["name"] for p in resp.get_json()["items"]]


def test_cashier_can_search_by_name_sku_and_barcode(client, cashier_headers, store):
    make_product(store, name="Amul Taaza Milk 1L", sku="MILK-001", barcode="8901262010012")
    make_product(store, name="Gokul Milk 500ml", sku="MILK-002")
    make_product(store, name="Parle-G Biscuit", sku="BISC-001")

    assert sorted(_search(client, cashier_headers, "milk")) == ["Amul Taaza Milk 1L", "Gokul Milk 500ml"]
    assert _search(client, cashier_headers, "bisc-0") == ["Parle-G Biscuit"]  # SKU, any case
    assert _search(client, cashier_headers, "8901262010012") == ["Amul Taaza Milk 1L"]  # exact barcode
    assert _search(client, cashier_headers, "chocolate") == []


def test_inactive_products_are_not_suggested(client, cashier_headers, store):
    p = make_product(store, name="Old Soap")
    p.is_active = False
    db.session.commit()
    assert _search(client, cashier_headers, "soap") == []
