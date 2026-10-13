"""Loose items (sugar, dal, rice): weighing-scale stickers, typed weights at billing, stock in kg."""
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.inventory import Inventory
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration

SUGAR_1250G = "2000123012505"  # 20 + 00123 + 01250 g + check digit
SUGAR_RS_52_50 = "2000123052505"  # price mode: 20 + 00123 + 05250 paise + check digit


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


@pytest.fixture
def sugar(client, admin_headers, store):
    resp = client.post("/api/v1/products", json={
        "name": "साखर", "price": "40", "tax_rate": "5", "uom": "kg", "is_variable_weight": True, "plu_code": "00123",
    }, headers=admin_headers)
    assert resp.status_code == 201, resp.get_json()
    product = resp.get_json()
    db.session.add(Inventory(store_id=store.id, product_id=product["id"], qty_on_hand=Decimal("50")))
    db.session.commit()
    return product


def _settings(client, admin_headers, **changes):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    return client.put("/api/v1/settings", json={**s, **changes}, headers=admin_headers)


def _scan(client, headers, code, store_id=None):
    params = {"barcode": code, **({"store_id": store_id} if store_id else {})}
    return client.get("/api/v1/products/scan", query_string=params, headers=headers)


def test_plu_is_saved_without_leading_zeros_and_unique(client, admin_headers, sugar):
    assert sugar["plu_code"] == "123"
    dup = client.post("/api/v1/products", json={
        "name": "Sugar 2", "price": "40", "is_variable_weight": True, "plu_code": "123",
    }, headers=admin_headers)
    assert dup.status_code == 409 and "साखर" in dup.get_json()["error"]["message"]

    packet = client.post("/api/v1/products", json={"name": "Biscuit", "price": "10", "plu_code": "77"}, headers=admin_headers)
    assert packet.status_code == 400  # only loose items have a scale code

    bad = client.post("/api/v1/products", json={"name": "Dal", "price": "90", "is_variable_weight": True, "plu_code": "12a"}, headers=admin_headers)
    assert bad.status_code == 422

    # Editing: clearing works, and unticking "loose item" drops the code.
    cleared = client.put(f"/api/v1/products/{sugar['id']}", json={"plu_code": ""}, headers=admin_headers).get_json()
    assert cleared["plu_code"] is None
    client.put(f"/api/v1/products/{sugar['id']}", json={"plu_code": "123"}, headers=admin_headers)
    packed = client.put(f"/api/v1/products/{sugar['id']}", json={"is_variable_weight": False}, headers=admin_headers).get_json()
    assert packed["plu_code"] is None


def test_scan_weight_sticker(client, cashier_headers, sugar, store):
    data = _scan(client, cashier_headers, SUGAR_1250G, store.id).get_json()
    assert data["product"]["id"] == sugar["id"]
    assert data["weight_kg"] == 1.25 and data["calculated_price"] == "50.00"  # ₹40/kg before GST


def test_scan_price_sticker_uses_store_price_and_gst(client, admin_headers, cashier_headers, sugar, store):
    assert _settings(client, admin_headers, scale_value="price").status_code == 200
    # This store sells at ₹40 + 5% GST = ₹42/kg, so a ₹52.50 sticker is 1.250 kg.
    assert _scan(client, cashier_headers, SUGAR_RS_52_50, store.id).get_json()["weight_kg"] == 1.25

    client.post("/api/v1/inventory/price", json={"store_id": store.id, "product_id": sugar["id"], "price": "50"}, headers=admin_headers)
    # ₹50 + 5% = ₹52.50/kg here, so the same sticker is exactly 1 kg.
    assert _scan(client, cashier_headers, SUGAR_RS_52_50, store.id).get_json()["weight_kg"] == 1.0


def test_other_scale_formats(client, admin_headers, cashier_headers, sugar, store):
    assert _settings(client, admin_headers, scale_prefix="21", scale_plu_digits=4).status_code == 200
    # 21 + 0123 + 001250 g + check digit
    assert _scan(client, cashier_headers, "2101230012504", store.id).get_json()["weight_kg"] == 1.25
    assert _settings(client, admin_headers, scale_prefix="29").status_code == 422  # in-house barcodes use 290
    assert _settings(client, admin_headers, scale_plu_digits=7).status_code == 422


def test_unknown_or_zero_stickers(client, cashier_headers, sugar, store):
    unknown = _scan(client, cashier_headers, "2000999012505", store.id)
    assert unknown.status_code == 404 and "999" in unknown.get_json()["error"]["message"]
    zero = _scan(client, cashier_headers, "2000123000005", store.id)
    assert zero.status_code == 400


def test_real_barcode_in_scale_range_still_scans(client, cashier_headers, store):
    p = make_product(store, name="Imported tea", barcode="2012345678901")
    data = _scan(client, cashier_headers, "2012345678901", store.id).get_json()
    assert data["product"]["id"] == p.id and data["weight_kg"] is None


def test_inactive_or_packet_product_not_matched_by_scale_code(client, admin_headers, cashier_headers, sugar, store):
    client.put(f"/api/v1/products/{sugar['id']}", json={"is_active": False}, headers=admin_headers)
    assert _scan(client, cashier_headers, SUGAR_1250G, store.id).status_code == 404


def test_old_setup_sku_as_scale_code_still_works(client, cashier_headers, store):
    p = make_product(store, name="Almonds", price="500", sku="00456", is_variable_weight=True)
    data = _scan(client, cashier_headers, "2000456015005", store.id).get_json()
    assert data["product"]["id"] == p.id and data["weight_kg"] == 1.5


def test_typed_weight_on_bill_and_stock_in_kg(client, cashier_headers, shift, sugar, store):
    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    sale = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": sugar["id"], "qty": "1.25"}, headers=cashier_headers).get_json()
    line = sale["items"][0]
    assert line["qty"] == 1.25 and line["is_variable_weight"] is True and line["uom"] == "kg"
    assert line["line_total"] == "50.00"

    line = client.put(f"/api/v1/sales/{sid}/items/{line['id']}", json={"qty": "2.5"}, headers=cashier_headers).get_json()["items"][0]
    assert line["qty"] == 2.5

    biscuit = make_product(store, name="Biscuit")
    resp = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": biscuit.id, "qty": "1.5"}, headers=cashier_headers)
    assert resp.status_code == 400 and "decimal" in resp.get_json()["error"]["message"]
    ok = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": biscuit.id, "qty": "2"}, headers=cashier_headers).get_json()
    biscuit_line = next(i for i in ok["items"] if i["product_id"] == biscuit.id)
    assert biscuit_line["uom"] == "pcs" and biscuit_line["is_variable_weight"] is False
    assert client.put(f"/api/v1/sales/{sid}/items/{biscuit_line['id']}", json={"qty": "0.5"}, headers=cashier_headers).status_code == 400

    paid = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "1000"}, headers=cashier_headers)
    assert paid.status_code == 200, paid.get_json()
    stock = db.session.scalar(db.select(Inventory.qty_on_hand).where(Inventory.product_id == sugar["id"]))
    assert stock == Decimal("47.500")

    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert receipt["items"][0]["uom"] == "kg" and receipt["items"][0]["is_variable_weight"] is True
