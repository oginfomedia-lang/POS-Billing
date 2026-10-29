"""Product search by sound: English letters find Marathi names, loose spellings find either script."""
import pytest

from app.extensions import db
from app.models.product import Product
from app.utils.search_key import search_key
from tests.factories import make_product

pytestmark = pytest.mark.integration


def _names(client, headers, q):
    items = client.get("/api/v1/products", query_string={"q": q, "per_page": 50}, headers=headers).get_json()["items"]
    return sorted(p["name"] for p in items)


@pytest.mark.parametrize("name, typed", [
    ("मधुर साखर", "madhur sakhar"), ("मधुर साखर", "madhoor"), ("मधुर साखर", "sakhar"), ("तांदूळ", "tandul"),
    ("Tandool", "tandul"), ("पाणी", "paani"), ("आंबा", "amba"), ("कांदा", "kanda"), ("लिंबू", "limbu"),
    ("कोथिंबीर", "kothimbir"), ("ज्ञान", "dnyan"), ("क्षेत्र", "kshetra"), ("चिकू", "chikku"), ("नमस्कार", "namaskar"),
    ("दूध", "doodh"), ("शेंगदाणे", "shengdane"),
])
def test_typed_spelling_matches_the_name(name, typed):
    assert search_key(typed) in search_key(name), (search_key(typed), search_key(name))


def test_pos_search_finds_marathi_names_typed_in_english(client, cashier_headers, store):
    make_product(store, name="मधुर साखर")
    make_product(store, name="तांदूळ कोलम")
    make_product(store, name="Tata Salt 1kg")
    assert _names(client, cashier_headers, "madhur") == ["मधुर साखर"]
    assert _names(client, cashier_headers, "sakhar") == ["मधुर साखर"]
    assert _names(client, cashier_headers, "tandul") == ["तांदूळ कोलम"]
    # The usual searches still work.
    assert _names(client, cashier_headers, "मधुर") == ["मधुर साखर"]
    assert _names(client, cashier_headers, "Tata") == ["Tata Salt 1kg"]
    assert _names(client, cashier_headers, "zzzz") == []


def test_stock_page_search_matches_the_products_search(client, admin_headers, store):
    make_product(store, name="मधुर साखर", sku="P-1")
    make_product(store, name="Tata Salt 1kg", sku="P-2")

    def stock_names(q=None):
        params = {"store_id": store.id, **({"q": q} if q is not None else {})}
        rows = client.get("/api/v1/inventory", query_string=params, headers=admin_headers).get_json()
        return sorted(r["product_name"] for r in rows)

    assert stock_names("sakhar") == ["मधुर साखर"]
    assert stock_names("मधुर") == ["मधुर साखर"]
    assert stock_names("tata") == ["Tata Salt 1kg"]
    assert stock_names("  ") == stock_names() == ["Tata Salt 1kg", "मधुर साखर"]


def test_key_follows_renames_and_imports_of_any_kind(client, admin_headers, store):
    pid = client.post("/api/v1/products", json={"name": "पोहे", "price": "40"}, headers=admin_headers).get_json()["id"]
    assert _names(client, admin_headers, "pohe") == ["पोहे"]
    client.put(f"/api/v1/products/{pid}", json={"name": "जाड पोहे"}, headers=admin_headers)
    assert _names(client, admin_headers, "jad pohe") == ["जाड पोहे"]
    assert db.session.get(Product, pid).search_key == search_key("जाड पोहे")


def test_a_one_letter_key_is_not_used(client, cashier_headers, store):
    make_product(store, name="क्षीर", sku="P-1")  # key "xir"
    assert _names(client, cashier_headers, "x") == []  # key "x" is too short to match by sound
    assert _names(client, cashier_headers, "kshir") == ["क्षीर"]


def test_special_characters_in_the_search_box_are_harmless(client, cashier_headers, store):
    make_product(store, name="मधुर साखर", sku="P-1")
    for q in ("%", "_", "' OR 1=1 --", "\\"):
        resp = client.get("/api/v1/products", query_string={"q": q}, headers=cashier_headers)
        assert resp.status_code == 200 and resp.get_json()["items"] == []
