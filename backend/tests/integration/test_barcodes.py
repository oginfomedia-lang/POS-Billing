"""In-house barcode generation (sequence-based) and product search."""
import pytest

from app.extensions import db
from app.models.enums import BarcodeType
from app.models.product import ProductBarcode
from app.utils.barcode_utils import generate_inhouse_barcode, validate_ean13
from tests.factories import make_product

pytestmark = pytest.mark.integration


def _generate(client, headers):
    resp = client.post("/api/v1/products/barcodes/generate", headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["barcode"]


def test_generated_codes_are_unique_valid_ean13(client, admin_headers):
    codes = [_generate(client, admin_headers) for _ in range(20)]
    assert len(set(codes)) == 20
    assert all(c.startswith("290") and validate_ean13(c) for c in codes)


def test_generator_skips_numbers_already_used(client, admin_headers, store):
    # Simulate codes made by the old SKU-digit generator occupying the next sequence numbers.
    next_n = db.session.scalar(db.text("SELECT last_value + CASE WHEN is_called THEN 1 ELSE 0 END FROM inhouse_barcode_seq"))
    p = make_product(store, barcode=generate_inhouse_barcode(next_n))
    db.session.add(ProductBarcode(product_id=p.id, barcode=generate_inhouse_barcode(next_n + 1), barcode_type=BarcodeType.IN_HOUSE))
    db.session.commit()
    assert _generate(client, admin_headers) == generate_inhouse_barcode(next_n + 2)


def test_products_with_similar_skus_get_different_codes(client, admin_headers, store):
    a = make_product(store, name="Milk 1L", sku="MILK-1L")
    b = make_product(store, name="Oil 1L", sku="OIL-1L")
    code_a = client.post(f"/api/v1/products/{a.id}/generate-inhouse-barcode", headers=admin_headers).get_json()["barcode"]
    code_b = client.post(f"/api/v1/products/{b.id}/generate-inhouse-barcode", headers=admin_headers).get_json()["barcode"]
    assert code_a != code_b


def test_generate_for_product_is_idempotent(client, admin_headers, store):
    p = make_product(store)
    first = client.post(f"/api/v1/products/{p.id}/generate-inhouse-barcode", headers=admin_headers).get_json()
    again = client.post(f"/api/v1/products/{p.id}/generate-inhouse-barcode", headers=admin_headers).get_json()
    assert first["barcode"] == again["barcode"]
    assert first["barcode_type"] == "IN_HOUSE"


def test_generated_code_can_be_saved_and_scanned(client, admin_headers, store):
    code = _generate(client, admin_headers)
    resp = client.post(
        "/api/v1/products",
        json={"name": "Loose Almonds 250g", "price": 250, "barcodes": [{"barcode": code, "barcode_type": "IN_HOUSE"}]},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.get_json()
    scan = client.get(f"/api/v1/pos/scan?barcode={code}", headers=admin_headers).get_json()
    assert scan["product"]["name"] == "Loose Almonds 250g"


def test_cashier_cannot_generate(client, cashier_headers):
    assert client.post("/api/v1/products/barcodes/generate", headers=cashier_headers).status_code == 403


def test_product_search(client, admin_headers, store):
    make_product(store, name="Amul Butter", sku="BUT-100", barcode="8901262150019")
    make_product(store, name="Bread", sku="BRD-1")
    names = lambda q: [p["name"] for p in client.get(f"/api/v1/products?q={q}", headers=admin_headers).get_json()["items"]]
    assert names("butter") == ["Amul Butter"]
    assert names("BRD") == ["Bread"]
    assert names("8901262150019") == ["Amul Butter"]
