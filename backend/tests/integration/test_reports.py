"""Reports, dashboard, settings, low-stock level and shift expected cash."""
from decimal import Decimal

import pytest

from tests.factories import make_counter, make_product, make_shift, pay_by_razorpay

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store, edc_device_id="TEST01|ezetap_android"), opening_float="500.00")


def _sell(client, headers, product, qty, method="cash", tendered="1000"):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    if method != "cash":
        resp = pay_by_razorpay(client, headers, sid, method)
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["sale"]
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": tendered}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_sales_report(client, admin_headers, cashier_headers, shift, store):
    milk = make_product(store, name="Milk", price="50.00", tax_rate="5.00")
    rice = make_product(store, name="Rice", price="200.00", tax_rate="12.00")
    _sell(client, cashier_headers, milk, 2)  # 100 + 5 tax
    _sell(client, cashier_headers, rice, 1, method="upi")  # 200 + 24 tax
    void_id = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    client.post(f"/api/v1/sales/{void_id}/items", json={"product_id": milk.id}, headers=cashier_headers)
    client.post(f"/api/v1/sales/{void_id}/void", headers=cashier_headers)

    r = client.get(f"/api/v1/reports/sales?store_id={store.id}", headers=admin_headers).get_json()
    s = r["summary"]
    assert (s["bills"], s["voided"], s["subtotal"], s["tax"], s["total"], s["average_bill"]) == (
        2, 1, "300.00", "29.00", "329.00", "164.50"
    )
    assert {m["method"]: m["amount"] for m in r["by_method"]} == {"cash": "105.00", "upi": "224.00"}
    assert len(r["daily"]) == 1 and r["daily"][0]["total"] == "329.00"
    gst = {g["tax_rate"]: g for g in r["gst"]}
    assert gst["12.00"]["taxable"] == "200.00" and gst["12.00"]["cgst"] == "12.00" and gst["12.00"]["sgst"] == "12.00"
    assert [p["product_name"] for p in r["top_products"]] == ["Rice", "Milk"]


def test_report_date_validation_and_permissions(client, admin_headers, cashier_headers):
    assert client.get("/api/v1/reports/sales?date_from=2026-02-01&date_to=2026-01-01", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/reports/sales?date_from=2024-01-01&date_to=2026-01-01", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/reports/sales?date_from=2020-01-01&date_to=2020-01-31", headers=admin_headers).get_json()["summary"]["bills"] == 0
    assert client.get("/api/v1/reports/sales", headers=cashier_headers).status_code == 403


def test_close_shift_expected_cash_and_shift_report(client, admin_headers, cashier_headers, shift, store):
    p = make_product(store, price="100.00", tax_rate="0")
    _sell(client, cashier_headers, p, 2, tendered="500")  # 200 cash kept (300 change given back)
    _sell(client, cashier_headers, p, 1, method="card")  # not cash
    resp = client.post(f"/api/v1/shifts/{shift.id}/close", json={"actual_cash": "690"}, headers=cashier_headers)
    assert resp.get_json()["expected_cash"] == "700.00"

    row = client.get(f"/api/v1/reports/shifts?store_id={store.id}", headers=admin_headers).get_json()[0]
    assert (row["bills"], row["cash_sales"], row["expected_cash"], row["actual_cash"], row["difference"]) == (
        2, "200.00", "700.00", "690.00", "-10.00"
    )
    assert row["counter_code"] == "C01"


def test_dashboard(client, admin_headers, cashier_headers, shift, store):
    p = make_product(store, price="10.00", tax_rate="0", stock=6)
    _sell(client, cashier_headers, p, 3)
    d = client.get(f"/api/v1/reports/dashboard?store_id={store.id}", headers=admin_headers).get_json()
    assert d["summary"]["bills"] == 1 and d["summary"]["total"] == "30.00"
    assert d["open_shifts"] == 1
    assert d["low_stock"] == 1  # 3 left <= default level 5
    assert d["recent_sales"][0]["cashier_name"] == "Test User"


def test_settings_defaults_update_and_receipt(client, admin_headers, cashier_headers, shift, store):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    assert s == {
        "receipt_header": "", "receipt_footer": "Thank you! Visit again.", "low_stock_threshold": "5", "return_window_days": 30,
        "rewards_enabled": False, "reward_rupees_per_point": "100", "reward_block_points": 100, "reward_block_value": "100",
        "daily_report_enabled": False, "daily_report_time": "22:30", "daily_report_mobiles": "",
        "ebill_enabled": False,
    }

    resp = client.put("/api/v1/settings", json={**s, "receipt_footer": "No returns after 7 days", "low_stock_threshold": "2"}, headers=admin_headers)
    assert resp.status_code == 200 and resp.get_json()["low_stock_threshold"] == "2"
    assert client.put("/api/v1/settings", json=s, headers=cashier_headers).status_code == 403

    p = make_product(store, price="10.00", tax_rate="0")
    sid = _sell(client, cashier_headers, p, 1)["id"]
    assert client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()["receipt_footer"] == "No returns after 7 days"

    audit = client.get("/api/v1/audit-logs?action=settings.update", headers=admin_headers).get_json()["items"]
    assert audit[0]["new_values"] == {"receipt_footer": "No returns after 7 days", "low_stock_threshold": "2"}


def test_low_stock_threshold_per_product(client, admin_headers, store):
    p = make_product(store, name="Eggs", stock=8)
    level = lambda: next(r for r in client.get(f"/api/v1/inventory?store_id={store.id}", headers=admin_headers).get_json() if r["product_name"] == "Eggs")
    assert level()["is_low"] is False  # 8 > default 5

    resp = client.post("/api/v1/inventory/threshold", json={"store_id": store.id, "product_id": p.id, "threshold": "10"}, headers=admin_headers)
    assert resp.status_code == 200
    row = level()
    assert (Decimal(row["low_stock_threshold"]), row["is_low"]) == (10, True)

    client.post("/api/v1/inventory/threshold", json={"store_id": store.id, "product_id": p.id, "threshold": None}, headers=admin_headers)
    row = level()
    assert row["low_stock_threshold"] is None and row["effective_threshold"] == "5" and row["is_low"] is False
