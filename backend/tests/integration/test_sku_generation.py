"""Automatic SKUs (CATEGORY-PRODUCT-NUMBER, e.g. KIR-SAK-0001): made by the server on save, unique across every
store, safe under simultaneous saves, never reused, and left alone by later edits.

The number comes from a database sequence that is not reset between tests, so tests compare numbers with each
other rather than expecting 0001."""
import re
import threading

import pytest

from app.errors.exceptions import ConflictError
from app.extensions import db
from app.models.category import Category
from app.models.product import Product, ProductBarcode
from app.schemas.product_schemas import ProductCreate
from app.services import product_service, sku_service
from tests.factories import make_store

pytestmark = pytest.mark.integration

SKU = re.compile(r"^([A-Z]{3})-([A-Z]{3})-(\d{4,})$")


def _category(name):
    cat = Category(name=name)
    db.session.add(cat)
    db.session.commit()
    return cat.id


def _create(client, headers, name, category_id=None, **extra):
    resp = client.post("/api/v1/products", json={"name": name, "price": "10", "category_id": category_id, **extra},
                       headers=headers)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _parts(sku):
    m = SKU.match(sku)
    assert m, sku
    return m.group(1), m.group(2), int(m.group(3))


@pytest.mark.parametrize("category, name, prefix", [
    ("Grocery", "Sugar", "GRO-SUG"),                 # English / English
    ("किराणा", "साखर", "KIR-SAK"),                    # Marathi / Marathi
    ("किराणा", "Sugar", "KIR-SUG"),                   # Marathi category, English product
    ("Grocery", "साखर", "GRO-SAK"),                   # English category, Marathi product
    ("पेये", "Coca कोला 1.25L", "PEY-COC"),            # mixed name with digits and punctuation
    ("दुग्धजन्य पदार्थ", "दूध", "DUG-DUD"),
    ("Personal Care", "केसांचे तेल", "PER-KES"),
])
def test_api_returns_the_generated_sku(client, admin_headers, category, name, prefix):
    product = _create(client, admin_headers, name, _category(category))
    assert product["sku"].startswith(prefix + "-") and SKU.match(product["sku"])
    # The names are kept exactly as typed; only the SKU uses English letters.
    saved = db.session.get(Product, product["id"])
    assert saved.name == name and saved.category.name == category


def test_no_category_or_no_usable_letters_use_fallbacks(client, admin_headers):
    assert _create(client, admin_headers, "Sugar")["sku"].startswith("CAT-SUG-")
    assert _create(client, admin_headers, "!!! 123", _category("???"))["sku"].startswith("CAT-PRD-")


def test_unknown_category_is_refused(client, admin_headers):
    resp = client.post("/api/v1/products", json={"name": "Sugar", "price": "10", "category_id": 99999},
                       headers=admin_headers)
    assert resp.status_code == 400 and "Category 99999 not found" in resp.get_json()["error"]["message"]
    assert db.session.query(Product).count() == 0


def test_same_name_same_category_and_different_categories_get_different_numbers(client, admin_headers):
    grocery, loose = _category("Grocery"), _category("Loose")
    a = _parts(_create(client, admin_headers, "Sugar", grocery)["sku"])
    b = _parts(_create(client, admin_headers, "Sugar", grocery)["sku"])
    c = _parts(_create(client, admin_headers, "Sugar", loose)["sku"])
    assert a[:2] == b[:2] == ("GRO", "SUG") and c[:2] == ("LOO", "SUG")
    assert a[2] < b[2] < c[2]  # one number line for everything


def test_a_deleted_products_number_is_not_used_again(client, admin_headers):
    cat = _category("Grocery")
    first = _create(client, admin_headers, "Sugar", cat)
    db.session.delete(db.session.get(Product, first["id"]))
    db.session.commit()
    second = _create(client, admin_headers, "Sugar", cat)
    assert _parts(second["sku"])[2] > _parts(first["sku"])[2]


def test_editing_name_or_category_keeps_the_sku(client, admin_headers):
    product = _create(client, admin_headers, "Sugar", _category("Grocery"))
    resp = client.put(f"/api/v1/products/{product['id']}",
                      json={"name": "साखर (सुटी)", "category_id": _category("Loose")}, headers=admin_headers)
    assert resp.status_code == 200 and resp.get_json()["sku"] == product["sku"]


def test_a_typed_sku_is_kept_and_checked(client, admin_headers):
    assert _create(client, admin_headers, "Sugar", sku="MY-OWN-1")["sku"] == "MY-OWN-1"
    dup = client.post("/api/v1/products", json={"name": "Salt", "price": "5", "sku": "MY-OWN-1"}, headers=admin_headers)
    assert dup.status_code == 409


def test_a_hand_typed_sku_with_the_next_number_is_skipped(client, admin_headers):
    cat = _category("Grocery")
    taken = sku_service.preview(cat, "Sugar")["sku"]  # what the next automatic SKU would be
    _create(client, admin_headers, "Other", sku=taken)
    product = _create(client, admin_headers, "Sugar", cat)
    assert product["sku"] != taken and _parts(product["sku"])[2] > _parts(taken)[2]


def test_barcode_stays_separate_from_the_sku(client, admin_headers):
    product = _create(client, admin_headers, "Parle-G", _category("Biscuits"), barcodes=["8901719101038"])
    assert product["sku"].startswith("BIS-PAR-")
    assert [b["barcode"] for b in product["barcodes"]] == ["8901719101038"]
    # Billing still finds it by its barcode, and by its new SKU.
    by_barcode = client.get("/api/v1/products/scan?barcode=8901719101038", headers=admin_headers)
    by_sku = client.get(f"/api/v1/products/scan?barcode={product['sku']}", headers=admin_headers)
    assert by_barcode.status_code == by_sku.status_code == 200
    assert by_barcode.get_json()["product"]["id"] == by_sku.get_json()["product"]["id"] == product["id"]


def test_preview_uses_no_number(client, admin_headers):
    cat = _category("किराणा")
    url = f"/api/v1/products/sku-preview?category_id={cat}&name=साखर"
    first = client.get(url, headers=admin_headers).get_json()
    again = client.get(url, headers=admin_headers).get_json()
    assert first == again and first["prefix"] == "KIR-SAK" and first["final"] is False
    assert _create(client, admin_headers, "साखर", cat)["sku"] == first["sku"]  # nobody saved in between


def test_preview_needs_permission(client, cashier_headers):
    assert client.get("/api/v1/products/sku-preview?name=Sugar", headers=cashier_headers).status_code == 403


def test_failed_save_leaves_nothing_behind(client, admin_headers):
    """A save that fails after its SKU was made (here: the barcode belongs to another product) saves nothing.
    Its number may be skipped, which is fine; the next product still gets a unique SKU."""
    cat = _category("Grocery")
    _create(client, admin_headers, "Salt", cat, barcodes=["8900000000017"])
    before = db.session.query(Product).count()
    resp = client.post("/api/v1/products", json={"name": "Sugar", "price": "10", "category_id": cat,
                                                 "barcodes": ["8900000000017"]}, headers=admin_headers)
    assert resp.status_code == 409
    assert db.session.query(Product).count() == before
    assert db.session.query(ProductBarcode).count() == 1
    assert SKU.match(_create(client, admin_headers, "Sugar", cat)["sku"])


def test_database_unique_constraint_backs_the_check(app, monkeypatch, store):
    """Two saves of the same typed SKU at the same moment: both pass the lookup, the database refuses the second,
    and the user gets "already exists" (409), not a server error, with nothing half-saved."""
    product_service.create_product(ProductCreate(name="First", price="10", sku="RACE-1"))
    monkeypatch.setattr(product_service.ProductRepository, "find_by_sku", lambda self, sku: None)
    with pytest.raises(ConflictError, match="RACE-1"):
        product_service.create_product(ProductCreate(name="Second", price="10", sku="RACE-1"))
    assert [p.name for p in db.session.query(Product).filter_by(sku="RACE-1")] == ["First"]


def test_simultaneous_saves_from_several_stores_and_counters(app):
    """Eight people in two stores each save five products at once (same category and names): forty different
    SKUs, forty different numbers, no errors."""
    stores = [make_store("Main").id, make_store("Branch").id]
    cat = _category("किराणा")
    made, errors = [], []
    start = threading.Barrier(8)

    def worker(n):
        with app.app_context():
            try:
                start.wait()
                for i in range(5):
                    p = product_service.create_product(ProductCreate(
                        name="साखर", price="42", category_id=cat, store_id=stores[n % 2]))
                    made.append(p.sku)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                db.session.remove()

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)

    assert errors == []
    assert len(made) == len(set(made)) == 40
    assert len({_parts(s)[2] for s in made}) == 40 and all(s.startswith("KIR-SAK-") for s in made)
    assert db.session.query(Product).count() == 40
