"""Bill limits: 3-decimal quantities, the 9999 per-line limit on merges, amounts too large for the money
columns, and manual-discount approval by a manager of another store."""
import pytest

from tests.factories import make_counter, make_product, make_shift, make_store, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _draft(client, headers):
    return client.post("/api/v1/sales", headers=headers).get_json()["id"]


def _add(client, headers, sid, product, qty):
    return client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)


def test_weight_rounded_to_grams_before_pricing(client, cashier_headers, shift, store):
    sugar = make_product(store, name="Sugar loose", price="42.00", tax_rate="0.00", is_variable_weight=True)
    sid = _draft(client, cashier_headers)
    line = _add(client, cashier_headers, sid, sugar, "1.2345").get_json()["items"][0]
    assert (line["qty"], line["line_total"]) == (1.235, "51.87")  # 42.00 × 1.235, not × 1.2345

    item = line["id"]
    line = client.put(f"/api/v1/sales/{sid}/items/{item}", json={"qty": "0.5004"}, headers=cashier_headers).get_json()["items"][0]
    assert (line["qty"], line["line_total"]) == (0.5, "21.00")
    assert _add(client, cashier_headers, sid, sugar, "0.0004").status_code == 422  # rounds to 0 g


def test_merged_line_cannot_pass_9999(client, cashier_headers, shift, store):
    bisc = make_product(store, name="Biscuit", price="10.00", stock=100000)
    sid = _draft(client, cashier_headers)
    assert _add(client, cashier_headers, sid, bisc, 9998).status_code == 200
    assert _add(client, cashier_headers, sid, bisc, 1).status_code == 200  # exactly 9999 is fine
    resp = _add(client, cashier_headers, sid, bisc, 1)
    assert resp.status_code == 400 and "at most 9999" in resp.get_json()["error"]["message"]
    sale = client.post(f"/api/v1/sales/{sid}/hold", json={}, headers=cashier_headers).get_json()
    assert sale["items"][0]["qty"] == 9999


def test_bill_too_large_for_money_columns_is_a_400(client, cashier_headers, shift, store):
    big = make_product(store, name="Big Ticket", price="9999999.99", tax_rate="28.00", stock=100000)
    sid = _draft(client, cashier_headers)
    resp = _add(client, cashier_headers, sid, big, 9999)
    assert resp.status_code == 400 and "too large" in resp.get_json()["error"]["message"]

    # The bill is untouched and still usable; a size that fits works, and so does raising it too far by edit.
    line = _add(client, cashier_headers, sid, big, 5).get_json()["items"][0]
    assert line["qty"] == 5
    resp = client.put(f"/api/v1/sales/{sid}/items/{line['id']}", json={"qty": 9000}, headers=cashier_headers)
    assert resp.status_code == 400
    assert client.post(f"/api/v1/sales/{sid}/hold", json={}, headers=cashier_headers).get_json()["items"][0]["qty"] == 5


def test_manual_discount_needs_a_manager_of_this_store(client, cashier_headers, shift, store):
    make_user(role="manager", username="mgr_here", pin="2468", store=store)
    make_user(role="manager", username="mgr_other", pin="2468", store=make_store(name="Branch 2"))
    make_user(role="admin", username="head_office", pin="2468")  # no store: may approve anywhere
    bisc = make_product(store, name="Biscuit", price="10.00")
    sid = _draft(client, cashier_headers)
    item = _add(client, cashier_headers, sid, bisc, 1).get_json()["items"][0]["id"]

    def approve(username):
        body = {"amount": "1", "reason": "damaged", "approver_username": username, "approver_pin": "2468"}
        return client.post(f"/api/v1/sales/{sid}/items/{item}/manual-discount", json=body, headers=cashier_headers)

    resp = approve("mgr_other")
    assert resp.status_code == 403 and "this store" in resp.get_json()["error"]["message"]
    assert approve("mgr_here").status_code == 200
    assert approve("head_office").status_code == 200
