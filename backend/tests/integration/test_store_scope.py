"""Multi-branch: each store's data is separate, branch users are locked to their store, per-store prices."""
import pytest

from tests.factories import make_counter, make_product, make_shift, make_store, make_user

pytestmark = pytest.mark.integration


def _login(client, username, pin):
    token = client.post("/api/v1/auth/login", json={"username": username, "pin": pin}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def other_store(app):
    return make_store(name="Pune Kothrud")


@pytest.fixture
def manager_headers(client, store):
    make_user(role="manager", username="mgr_a", pin="4321", store=store)
    return _login(client, "mgr_a", "4321")


def test_manager_cannot_read_another_store(client, manager_headers, store, other_store):
    other = other_store.id
    assert client.get(f"/api/v1/inventory?store_id={other}", headers=manager_headers).status_code == 403
    assert client.get(f"/api/v1/reports/dashboard?store_id={other}", headers=manager_headers).status_code == 403
    assert client.get(f"/api/v1/reports/sales?store_id={other}", headers=manager_headers).status_code == 403
    assert client.get(f"/api/v1/stores/{other}/counters", headers=manager_headers).status_code == 403
    # Own store still works, and "no store" means their own store.
    assert client.get(f"/api/v1/inventory?store_id={store.id}", headers=manager_headers).status_code == 200
    assert client.get("/api/v1/reports/dashboard", headers=manager_headers).get_json()["store_id"] == store.id


def test_manager_cannot_change_another_stores_stock(client, manager_headers, other_store):
    p = make_product(other_store)
    body = {"store_id": other_store.id, "product_id": p.id, "qty": "5"}
    assert client.post("/api/v1/inventory/stock-in", json=body, headers=manager_headers).status_code == 403


def test_lists_are_limited_to_own_store(client, manager_headers, store, other_store):
    make_user(role="cashier", username="cash_b", store=other_store)
    make_user(role="cashier", username="cash_a", store=store)
    stores = client.get("/api/v1/stores", headers=manager_headers).get_json()["items"]
    assert [s["id"] for s in stores] == [store.id]
    users = client.get("/api/v1/users", headers=manager_headers).get_json()["items"]
    assert "cash_b" not in [u["username"] for u in users]
    assert "cash_a" in [u["username"] for u in users]


def test_admin_sees_every_store(client, admin_headers, store, other_store):
    stores = client.get("/api/v1/stores", headers=admin_headers).get_json()["items"]
    assert {store.id, other_store.id} <= {s["id"] for s in stores}
    assert client.get(f"/api/v1/inventory?store_id={other_store.id}", headers=admin_headers).status_code == 200


def test_manager_offers_are_own_store_only(client, manager_headers, admin_headers, store, other_store):
    base = {"name": "x", "discount_type": "percentage", "value": "5", "scope": "bill"}
    assert client.post("/api/v1/discounts", json={**base, "store_id": other_store.id}, headers=manager_headers).status_code == 403
    assert client.post("/api/v1/discounts", json=base, headers=manager_headers).status_code == 403  # all-stores offer
    assert client.post("/api/v1/discounts", json={**base, "store_id": store.id}, headers=manager_headers).status_code == 201
    # Head office's offer for the other branch is invisible to this manager.
    client.post("/api/v1/discounts", json={**base, "name": "Kothrud only", "store_id": other_store.id}, headers=admin_headers)
    names = [d["name"] for d in client.get("/api/v1/discounts", headers=manager_headers).get_json()]
    assert "Kothrud only" not in names


def test_store_price_used_only_in_that_store(client, admin_headers, store, other_store):
    p = make_product(store, name="Milk", price="50.00", tax_rate="0")
    resp = client.post("/api/v1/inventory/price", json={"store_id": store.id, "product_id": p.id, "price": "45.00"}, headers=admin_headers)
    assert resp.status_code == 200

    levels = client.get(f"/api/v1/inventory?store_id={store.id}", headers=admin_headers).get_json()
    milk = next(r for r in levels if r["product_id"] == p.id)
    assert (milk["base_price"], milk["store_price"], milk["price"]) == ("50.00", "45.00", "45.00")
    listed = client.get(f"/api/v1/products?store_id={store.id}", headers=admin_headers).get_json()["items"]
    assert next(x for x in listed if x["id"] == p.id)["store_price"] == "45.00"

    # A cashier in this store is billed the store price.
    cashier = make_user(role="cashier", username="till_a", pin="1111", store=store)
    make_shift(cashier, make_counter(store))
    headers = _login(client, "till_a", "1111")
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    sale = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": p.id, "qty": 1}, headers=headers).get_json()
    assert sale["items"][0]["unit_price"] == "45.00"

    # Another store still sells at the head-office price; clearing the override restores it.
    other_levels = client.get(f"/api/v1/inventory?store_id={other_store.id}", headers=admin_headers).get_json()
    assert next(r for r in other_levels if r["product_id"] == p.id)["price"] == "50.00"
    client.post("/api/v1/inventory/price", json={"store_id": store.id, "product_id": p.id, "price": None}, headers=admin_headers)
    levels = client.get(f"/api/v1/inventory?store_id={store.id}", headers=admin_headers).get_json()
    assert next(r for r in levels if r["product_id"] == p.id)["price"] == "50.00"
