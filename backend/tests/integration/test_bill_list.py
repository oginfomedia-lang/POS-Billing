"""Bills / returns lists behind the dashboard and report tiles: same numbers as the sales report."""
import pytest

from tests.factories import make_counter, make_product, make_shift, make_store, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _sell(client, headers, product, qty=1, method="cash", reference=None):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    body = {"method": method, "cash_tendered": "10000"} if method == "cash" else {"method": method, "reference": reference}
    resp = client.post(f"/api/v1/sales/{sid}/complete", json=body, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _bills(client, headers, **params):
    resp = client.get("/api/v1/reports/bills", query_string=params, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_bill_list_matches_sales_report(client, admin_headers, cashier_headers, shift, store):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    client.put("/api/v1/settings", json={**s, "card_upi_mode": "manual"}, headers=admin_headers)
    oil = make_product(store, name="Oil", price="100.00", tax_rate="5.00")
    soap = make_product(store, name="Soap", price="30.00", tax_rate="18.00")
    first = _sell(client, cashier_headers, oil, 2)
    _sell(client, cashier_headers, soap, 1, method="upi", reference="UTR1")
    voided = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    client.post(f"/api/v1/sales/{voided}/items", json={"product_id": soap.id}, headers=cashier_headers)
    client.post(f"/api/v1/sales/{voided}/void", headers=cashier_headers)

    report = client.get(f"/api/v1/reports/sales?store_id={store.id}", headers=admin_headers).get_json()["summary"]
    data = _bills(client, admin_headers, store_id=store.id)
    assert data["totals"]["count"] == report["bills"] == 2
    for key, rkey in (("total", "total"), ("tax", "tax"), ("discount", "discount"), ("subtotal", "subtotal")):
        assert data["totals"][key] == report[rkey], key
    assert data["items"][1]["bill_number"] == first["bill_number"]  # newest first
    assert data["items"][1]["methods"] == ["cash"] and data["items"][1]["items_count"] == 1

    assert [b["methods"] for b in _bills(client, admin_headers, method="upi")["items"]] == [["upi"]]
    v = _bills(client, admin_headers, status="voided")
    assert v["totals"]["count"] == report["voided"] == 1 and v["items"][0]["status"] == "voided"
    assert _bills(client, admin_headers, q=first["bill_number"][-4:])["totals"]["count"] == 1


def test_discounted_filter(client, admin_headers, cashier_headers, shift, store):
    make_user(role="manager", username="mgr", pin="2468", store=store)
    p = make_product(store, name="Rice", price="50.00", tax_rate="0.00")
    _sell(client, cashier_headers, p)
    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    item = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": p.id}, headers=cashier_headers).get_json()["items"][0]["id"]
    client.post(f"/api/v1/sales/{sid}/items/{item}/manual-discount", headers=cashier_headers,
                json={"amount": "5", "reason": "damaged", "approver_username": "mgr", "approver_pin": "2468"})
    client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "100"}, headers=cashier_headers)

    d = _bills(client, admin_headers, discounted="true")
    assert d["totals"]["count"] == 1 and d["totals"]["discount"] == "5.00"


def test_returns_list_matches_returns_tile(client, admin_headers, cashier_headers, shift, store):
    make_user(role="manager", username="mgr", pin="2468", store=store)
    p = make_product(store, name="Oil", price="100.00", tax_rate="0.00")
    sale = _sell(client, cashier_headers, p, 3)
    client.post("/api/v1/returns", headers=cashier_headers, json={
        "bill_number": sale["bill_number"], "lines": [{"sale_item_id": sale["items"][0]["id"], "qty": 1}],
        "reason": "Damaged", "approver_username": "mgr", "approver_pin": "2468"})
    report = client.get(f"/api/v1/reports/sales?store_id={store.id}", headers=admin_headers).get_json()["summary"]
    data = client.get("/api/v1/reports/returns", query_string={"store_id": store.id}, headers=admin_headers).get_json()
    assert (data["totals"]["count"], data["totals"]["total"]) == (report["returns"], report["refunded"]) == (1, "100.00")
    row = data["items"][0]
    assert row["bill_number"] == sale["bill_number"] and row["approved_by_name"] and row["items_count"] == 1
    # The bill shows what was refunded on it.
    assert _bills(client, admin_headers)["items"][0]["refunded"] == "100.00"


def test_store_scope_and_paging(client, admin_headers, cashier_headers, shift, store):
    p = make_product(store, name="Tea", price="10.00", tax_rate="0.00")
    for _ in range(3):
        _sell(client, cashier_headers, p)
    page2 = _bills(client, admin_headers, per_page=2, page=2)
    assert (page2["pages"], len(page2["items"]), page2["totals"]["count"]) == (2, 1, 3)

    other = make_store(name="Branch 2")
    make_user(role="manager", username="mgr_b", pin="2468", store=other)
    token = client.post("/api/v1/auth/login", json={"username": "mgr_b", "pin": "2468"}).get_json()["access_token"]
    mgr_b = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/reports/bills", headers=mgr_b).get_json()["totals"]["count"] == 0  # own store only
    assert client.get(f"/api/v1/reports/bills?store_id={store.id}", headers=mgr_b).status_code == 403
    assert client.get("/api/v1/reports/bills", headers=cashier_headers).status_code == 403
