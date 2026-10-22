"""Store-wise counters and staff, and no cross-store access to shifts, bills, credit notes or staff."""
import pytest

from tests.factories import make_counter, make_product, make_shift, make_store, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def stores(app):
    return make_store(name="Store A"), make_store(name="Store B")


def _login(client, username, pin="2468"):
    token = client.post("/api/v1/auth/login", json={"username": username, "pin": pin}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _counter(client, headers, store, code, label):
    return client.post(f"/api/v1/stores/{store.id}/counters", json={"code": code, "label": label}, headers=headers)


def _user(client, headers, username, store, full_name="Rahul", role="cashier"):
    body = {"username": username, "full_name": full_name, "pin": "2468", "role": role,
            "store_id": store.id if store else None}
    return client.post("/api/v1/users", json=body, headers=headers)


def _error(resp):
    return resp.get_json()["error"]["message"]


# ── Counters ─────────────────────────────────────────────────────────────────

def test_each_store_has_its_own_counter_1(client, admin_headers, stores):
    a, b = stores
    assert _counter(client, admin_headers, a, "C01", "Counter 1").status_code == 201
    assert _counter(client, admin_headers, b, "C01", "Counter 1").status_code == 201  # same code + name, other store

    dup = _counter(client, admin_headers, a, "C01", "Front till")
    assert dup.status_code == 409 and "already exists in Store A" in _error(dup)
    same_name = _counter(client, admin_headers, a, "C02", "counter 1")  # name check ignores letter case
    assert same_name.status_code == 409 and "named 'counter 1'" in _error(same_name)

    assert [c["code"] for c in client.get(f"/api/v1/stores/{a.id}/counters", headers=admin_headers).get_json()] == ["C01"]
    assert [c["code"] for c in client.get(f"/api/v1/stores/{b.id}/counters", headers=admin_headers).get_json()] == ["C01"]


def test_renaming_a_counter_to_a_name_used_in_its_store_is_refused(client, admin_headers, stores):
    a, b = stores
    _counter(client, admin_headers, a, "C01", "Counter 1")
    second = _counter(client, admin_headers, a, "C02", "Counter 2").get_json()
    _counter(client, admin_headers, b, "C01", "Billing")

    resp = client.put(f"/api/v1/stores/{a.id}/counters/{second['id']}", json={"label": "Counter 1"}, headers=admin_headers)
    assert resp.status_code == 409
    ok = client.put(f"/api/v1/stores/{a.id}/counters/{second['id']}", json={"label": "Billing"}, headers=admin_headers)
    assert ok.status_code == 200  # "Billing" is only used in Store B


def test_counters_of_another_store_are_hidden_from_its_staff(client, stores):
    a, b = stores
    make_counter(a, code="C01")
    make_user(role="manager", username="mgr_b", pin="2468", store=b)
    mgr_b = _login(client, "mgr_b")
    assert client.get(f"/api/v1/stores/{a.id}/counters", headers=mgr_b).status_code == 403
    assert client.get(f"/api/v1/stores/{b.id}/counters", headers=mgr_b).status_code == 200


# ── Users ────────────────────────────────────────────────────────────────────

def test_same_full_name_in_different_stores_but_login_names_stay_unique(client, admin_headers, stores):
    a, b = stores
    ra = _user(client, admin_headers, "rahul_a", a)
    rb = _user(client, admin_headers, "rahul_b", b)
    assert (ra.status_code, rb.status_code) == (201, 201)
    assert (ra.get_json()["full_name"], rb.get_json()["full_name"]) == ("Rahul", "Rahul")

    # Login is username + PIN with no store, so a login name can't repeat anywhere.
    dup = _user(client, admin_headers, "rahul_a", b)
    assert dup.status_code == 409 and "already taken by Rahul at Store A" in _error(dup)
    assert _user(client, admin_headers, "rahul_a", a).status_code == 409

    # Both log in to their own store.
    assert client.get("/api/v1/auth/me", headers=_login(client, "rahul_a")).get_json()["store_id"] == a.id
    assert client.get("/api/v1/auth/me", headers=_login(client, "rahul_b")).get_json()["store_id"] == b.id


def test_staff_must_belong_to_an_existing_active_store(client, admin_headers, stores):
    a, _ = stores
    no_store = _user(client, admin_headers, "nostore", None)
    assert no_store.status_code == 400 and "store" in _error(no_store)
    assert _user(client, admin_headers, "nostore_admin", None, role="admin").status_code == 201  # head office

    bad = client.post("/api/v1/users", json={"username": "ghost", "full_name": "G", "pin": "2468",
                                             "role": "cashier", "store_id": 999999}, headers=admin_headers)
    assert bad.status_code == 400

    closed = make_store(name="Closed", is_active=False)
    assert _user(client, admin_headers, "late", closed).status_code == 400

    uid = _user(client, admin_headers, "rahul_a", a).get_json()["id"]
    moved = client.put(f"/api/v1/users/{uid}", json={"store_id": 999999}, headers=admin_headers)
    assert moved.status_code == 400


def test_a_manager_cannot_see_another_stores_staff(client, admin_headers, stores):
    a, b = stores
    ua = _user(client, admin_headers, "rahul_a", a).get_json()
    _user(client, admin_headers, "rahul_b", b)
    make_user(role="manager", username="mgr_b", pin="2468", store=b)
    mgr_b = _login(client, "mgr_b")

    assert client.get(f"/api/v1/users/{ua['id']}", headers=mgr_b).status_code == 404
    listed = client.get("/api/v1/users", headers=mgr_b).get_json()["items"]
    assert {u["username"] for u in listed} == {"rahul_b", "mgr_b"}
    assert client.get(f"/api/v1/users?store_id={a.id}", headers=mgr_b).status_code == 403
    assert client.get(f"/api/v1/users/{ua['id']}", headers=admin_headers).status_code == 200


# ── Shifts ───────────────────────────────────────────────────────────────────

def test_shift_needs_own_store_and_a_counter_of_that_store(client, admin_headers, stores):
    a, b = stores
    counter_a = make_counter(a, code="C01")
    counter_b = make_counter(b, code="C01")
    make_user(role="cashier", username="cash_b", pin="2468", store=b)
    cash_b = _login(client, "cash_b")

    wrong_counter = client.post("/api/v1/shifts/open", json={"store_id": b.id, "counter_id": counter_a.id}, headers=cash_b)
    assert wrong_counter.status_code == 404
    other_store = client.post("/api/v1/shifts/open", json={"store_id": a.id, "counter_id": counter_a.id}, headers=cash_b)
    assert other_store.status_code == 403
    assert client.post("/api/v1/shifts/open", json={"store_id": 987654}, headers=cash_b).status_code == 404

    ok = client.post("/api/v1/shifts/open", json={"store_id": b.id, "counter_id": counter_b.id}, headers=cash_b)
    assert ok.status_code == 201 and ok.get_json()["counter_id"] == counter_b.id
    # Head office may open a shift in any store.
    assert client.post("/api/v1/shifts/open", json={"store_id": a.id, "counter_id": counter_a.id},
                       headers=admin_headers).status_code == 201


# ── Bills, credit notes, shift lists ─────────────────────────────────────────

def test_another_stores_bill_shift_and_credit_note_are_not_visible(client, admin_headers, stores):
    a, b = stores
    cash_a = make_user(role="cashier", username="cash_a", pin="2468", store=a)
    make_user(role="manager", username="mgr_a", pin="2468", store=a)
    make_user(role="manager", username="mgr_b", pin="2468", store=b)
    make_user(role="cashier", username="cash_b", pin="2468", store=b)
    shift_a = make_shift(cash_a, make_counter(a, code="C01"))
    p = make_product(a, name="Oil", price="100.00", tax_rate="0.00")
    ha, mgr_b, cash_b = _login(client, "cash_a"), _login(client, "mgr_b"), _login(client, "cash_b")

    sid = client.post("/api/v1/sales", headers=ha).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": p.id, "qty": 2}, headers=ha)
    client.put(f"/api/v1/sales/{sid}/customer-mobile", json={"mobile": "9988776655"}, headers=ha)
    sale = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "500"}, headers=ha).get_json()
    ret = client.post("/api/v1/returns", json={
        "bill_number": sale["bill_number"], "lines": [{"sale_item_id": sale["items"][0]["id"], "qty": 1}],
        "reason": "Damaged", "approver_username": "mgr_a", "approver_pin": "2468",
    }, headers=ha).get_json()

    for headers in (mgr_b, cash_b):
        assert client.get(f"/api/v1/sales/{sid}/receipt", headers=headers).status_code == 404
        assert client.get(f"/api/v1/returns/{ret['id']}", headers=headers).status_code == 404
        assert client.get(f"/api/v1/shifts/{shift_a.id}/bills", headers=headers).status_code == 404
    assert client.post(f"/api/v1/sales/{sid}/ebill", json={"mobile": "9988776655"}, headers=cash_b).status_code == 404

    # Own store and head office still see them.
    assert client.get(f"/api/v1/sales/{sid}/receipt", headers=ha).status_code == 200
    assert client.get(f"/api/v1/returns/{ret['id']}", headers=ha).status_code == 200
    assert client.get(f"/api/v1/sales/{sid}/receipt", headers=admin_headers).status_code == 200
    assert client.get(f"/api/v1/shifts/{shift_a.id}/bills", headers=admin_headers).status_code == 200
