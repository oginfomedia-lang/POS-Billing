"""Categories: create, edit (rename, move, deactivate) and delete."""
from tests.factories import make_product

URL = "/api/v1/categories"


def create(client, headers, name, parent_id=None):
    return client.post(URL, json={"name": name, "parent_id": parent_id}, headers=headers)


def test_create_trims_and_rejects_duplicates(client, admin_headers):
    resp = create(client, admin_headers, "  Dairy   Products ")
    assert resp.status_code == 201
    assert resp.get_json()["name"] == "Dairy Products"
    assert create(client, admin_headers, "dairy products").status_code == 409
    assert create(client, admin_headers, "   ").status_code == 422


def test_rename_move_and_back_to_top_level(client, admin_headers):
    dairy = create(client, admin_headers, "Dairy").get_json()
    milk = create(client, admin_headers, "Milk").get_json()

    resp = client.put(f"{URL}/{milk['id']}", json={"name": "Fresh Milk", "parent_id": dairy["id"]}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Fresh Milk" and resp.get_json()["parent_id"] == dairy["id"]

    resp = client.put(f"{URL}/{milk['id']}", json={"parent_id": None}, headers=admin_headers)
    assert resp.get_json()["parent_id"] is None


def test_rename_to_existing_name_refused(client, admin_headers):
    create(client, admin_headers, "Snacks")
    drinks = create(client, admin_headers, "Drinks").get_json()
    resp = client.put(f"{URL}/{drinks['id']}", json={"name": "SNACKS"}, headers=admin_headers)
    assert resp.status_code == 409


def test_no_loops(client, admin_headers):
    a = create(client, admin_headers, "A").get_json()
    b = create(client, admin_headers, "B", parent_id=a["id"]).get_json()
    assert client.put(f"{URL}/{a['id']}", json={"parent_id": a["id"]}, headers=admin_headers).status_code == 400
    assert client.put(f"{URL}/{a['id']}", json={"parent_id": b["id"]}, headers=admin_headers).status_code == 400


def test_deactivate(client, admin_headers):
    cat = create(client, admin_headers, "Seasonal").get_json()
    resp = client.put(f"{URL}/{cat['id']}", json={"is_active": False}, headers=admin_headers)
    assert resp.get_json()["is_active"] is False


def test_delete_unused(client, admin_headers):
    cat = create(client, admin_headers, "Old").get_json()
    assert client.delete(f"{URL}/{cat['id']}", headers=admin_headers).status_code == 204
    assert all(c["id"] != cat["id"] for c in client.get(URL, headers=admin_headers).get_json())


def test_delete_in_use_refused(client, admin_headers, store):
    from app.extensions import db

    parent = create(client, admin_headers, "Grocery").get_json()
    create(client, admin_headers, "Rice", parent_id=parent["id"])
    resp = client.delete(f"{URL}/{parent['id']}", headers=admin_headers)
    assert resp.status_code == 409
    assert "sub-category" in resp.get_json()["error"]["message"]

    used = create(client, admin_headers, "Oil").get_json()
    product = make_product(store, name="Sunflower Oil")
    product.category_id = used["id"]
    db.session.commit()
    resp = client.delete(f"{URL}/{used['id']}", headers=admin_headers)
    assert resp.status_code == 409
    assert "1 product" in resp.get_json()["error"]["message"]


def test_cashier_cannot_delete(client, admin_headers, cashier_headers):
    cat = create(client, admin_headers, "Locked").get_json()
    assert client.delete(f"{URL}/{cat['id']}", headers=cashier_headers).status_code == 403
