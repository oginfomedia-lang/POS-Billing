"""Collection per cashier/counter report and the nightly WhatsApp summary (sent once, retried, manual send)."""
import pytest

from app.errors.exceptions import AppError
from app.services import daily_report_service, whatsapp_gateway
from app.utils.dates import now_ist
from tests.factories import make_counter, make_product, make_shift, make_user, pay_by_razorpay

pytestmark = pytest.mark.integration


def _login(client, username, pin):
    token = client.post("/api/v1/auth/login", json={"username": username, "pin": pin}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _sell(client, headers, product, qty=1, method="cash"):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    if method != "cash":
        resp = pay_by_razorpay(client, headers, sid, method)
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()["sale"]
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "1000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


@pytest.fixture
def two_counters(client, cashier_user, cashier_headers, store):
    """Cashier 1 on C01: cash 100 + UPI 200, one 100 return, shift still open.
    Cashier 2 on C02: cash 50 + card 300, shift closed ₹10 short."""
    c1 = make_counter(store, code="C01", edc_device_id="TEST01|ezetap_android")
    c2 = make_counter(store, code="C02", label="Counter 2", edc_device_id="TEST02|ezetap_android")
    make_user(role="manager", username="mgr", pin="4321", store=store)
    cashier2 = make_user(role="cashier", username="cashier2", pin="2468", store=store)
    make_shift(cashier_user, c1)
    shift2 = make_shift(cashier2, c2)
    h2 = _login(client, "cashier2", "2468")

    p100 = make_product(store, name="Ghee", price="100.00", tax_rate="0")
    sale = _sell(client, cashier_headers, p100)
    _sell(client, cashier_headers, make_product(store, name="Rice", price="200.00", tax_rate="0"), method="upi")
    resp = client.post("/api/v1/returns", json={
        "bill_number": sale["bill_number"], "lines": [{"sale_item_id": sale["items"][0]["id"], "qty": 1}],
        "reason": "Damaged", "approver_username": "mgr", "approver_pin": "4321",
    }, headers=cashier_headers)
    assert resp.status_code == 201, resp.get_json()

    _sell(client, h2, make_product(store, name="Salt", price="50.00", tax_rate="0"))
    _sell(client, h2, make_product(store, name="Oil", price="300.00", tax_rate="0"), method="card")
    resp = client.post(f"/api/v1/shifts/{shift2.id}/close", json={"actual_cash": "40"}, headers=h2)
    assert resp.status_code == 200, resp.get_json()


def test_collection_report_per_cashier_and_counter(client, admin_headers, store, two_counters):
    r = client.get(f"/api/v1/reports/collection?store_id={store.id}", headers=admin_headers).get_json()
    rows = {row["counter_code"]: row for row in r["rows"]}
    c1, c2 = rows["C01"], rows["C02"]
    assert (c1["bills"], c1["cash"], c1["upi"], c1["card"], c1["total"], c1["refunds"], c1["net"]) == (
        2, "100.00", "200.00", "0.00", "300.00", "100.00", "200.00"
    )
    assert c1["shift_open"] is True and c1["cash_difference"] is None
    assert (c2["bills"], c2["cash"], c2["card"], c2["total"], c2["net"], c2["cash_difference"], c2["shift_open"]) == (
        2, "50.00", "300.00", "350.00", "350.00", "-10.00", False
    )
    assert [row["counter_code"] for row in r["rows"]] == ["C02", "C01"]  # biggest net first
    assert r["totals"] == {
        "bills": 4, "cash": "150.00", "card": "300.00", "upi": "200.00", "total": "650.00", "refunds": "100.00", "net": "550.00"
    }


def test_collection_report_permissions(client, cashier_headers):
    assert client.get("/api/v1/reports/collection", headers=cashier_headers).status_code == 403


def test_inr_format():
    assert daily_report_service.inr("1234567.5") == "₹12,34,567.50"
    assert daily_report_service.inr("4000") == "₹4,000"
    assert daily_report_service.inr("-10") == "-₹10"


def _enable(client, admin_headers, mobiles="+91 98765 43210"):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    resp = client.put("/api/v1/settings", json={
        **s, "daily_report_enabled": True, "daily_report_time": "22:30", "daily_report_mobiles": mobiles,
    }, headers=admin_headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_settings_validate_mobiles(client, admin_headers):
    assert _enable(client, admin_headers, "+91 98765 43210, 9123456789,9876543210")["daily_report_mobiles"] == "9876543210,9123456789"
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    assert client.put("/api/v1/settings", json={**s, "daily_report_mobiles": "12345"}, headers=admin_headers).status_code == 422
    assert client.put("/api/v1/settings", json={**s, "daily_report_time": "25:00"}, headers=admin_headers).status_code == 422


def test_nightly_send_once_after_the_set_time(client, admin_headers, store, two_counters, monkeypatch):
    sent = []
    monkeypatch.setattr(whatsapp_gateway, "send_template", lambda mobile, params: sent.append((mobile, params)) or "wamid.1")

    assert daily_report_service.run_due(now_ist().replace(hour=23)) == []  # switched off by default
    _enable(client, admin_headers)
    assert daily_report_service.run_due(now_ist().replace(hour=22, minute=29)) == []  # not time yet

    results = daily_report_service.run_due(now_ist().replace(hour=22, minute=45))
    assert [(r.recipient, r.status) for r in results] == [("9876543210", "sent")]
    mobile, params = sent[0]
    assert params[0] == "Test Store" and params[3:] == ["₹650", "₹100", "₹550"]
    assert "(C02): ₹350, 2 bills (Cash ₹50, UPI ₹0, Card ₹300) [cash short ₹10]" in params[2]
    assert "(C01): ₹200" in params[2] and "[shift still open]" in params[2]

    assert daily_report_service.run_due(now_ist().replace(hour=23)) == []  # already sent: never twice
    assert len(sent) == 1


def test_failed_send_is_retried_three_times(client, admin_headers, store, monkeypatch):
    def fail(mobile, params):
        raise AppError("Cannot reach WhatsApp. Check the internet connection.")

    monkeypatch.setattr(whatsapp_gateway, "send_template", fail)
    _enable(client, admin_headers)
    late = now_ist().replace(hour=23)
    for _ in range(3):
        assert [r.status for r in daily_report_service.run_due(late)] == ["failed"]
    assert daily_report_service.run_due(late) == []  # gave up after 3 tries

    logs = client.get("/api/v1/settings/daily-report/logs", headers=admin_headers).get_json()
    assert (logs[0]["status"], logs[0]["attempts"], logs[0]["error"]) == ("failed", 3, "Cannot reach WhatsApp. Check the internet connection.")
    assert "No sales." in logs[0]["body"]


def test_send_now_button(client, admin_headers, cashier_headers, store):
    resp = client.post("/api/v1/settings/daily-report/send", headers=admin_headers)
    assert resp.status_code == 400 and "mobile" in resp.get_json()["error"]["message"]

    _enable(client, admin_headers)
    for _ in range(2):  # can be pressed again
        resp = client.post("/api/v1/settings/daily-report/send", headers=admin_headers)
        assert resp.status_code == 200 and resp.get_json()[0]["status"] == "sent"
    assert client.post("/api/v1/settings/daily-report/send", headers=cashier_headers).status_code == 403

    # The manual send doesn't count as tonight's automatic one.
    assert [r.status for r in daily_report_service.run_due(now_ist().replace(hour=23))] == ["sent"]
