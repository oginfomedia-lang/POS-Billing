"""WhatsApp e-bill: PDF of the paid bill sent to the customer's mobile, retried, and resent from the bill screen."""
import pytest

from app.extensions import db
from app.models.notification import NotificationLog
from app.models.sale import Sale
from app.services import ebill_service, whatsapp_gateway
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


@pytest.fixture
def sent(monkeypatch):
    """Records what would go to WhatsApp."""
    out = []
    monkeypatch.setattr(whatsapp_gateway, "upload_media", lambda data, filename: f"media-{filename}")
    monkeypatch.setattr(
        whatsapp_gateway, "send_template",
        lambda mobile, params, template=None, document=None: out.append((mobile, params, template, document)) or "wamid.1",
    )
    return out


def _enable(client, admin_headers, on=True):
    s = client.get("/api/v1/settings", headers=admin_headers).get_json()
    assert client.put("/api/v1/settings", json={**s, "ebill_enabled": on}, headers=admin_headers).status_code == 200


def _paid_bill(client, headers, store, mobile="9876543210", name="तांदूळ बासमती"):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": make_product(store, name=name).id, "qty": 1}, headers=headers)
    if mobile:
        client.put(f"/api/v1/sales/{sid}/customer-mobile", json={"mobile": mobile}, headers=headers)
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "1000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _logs():
    return db.session.scalars(db.select(NotificationLog).order_by(NotificationLog.id)).all()


def test_paid_bill_sends_pdf_ebill(client, admin_headers, cashier_headers, shift, store, sent):
    _enable(client, admin_headers)
    bill = _paid_bill(client, cashier_headers, store)

    assert len(sent) == 1
    mobile, params, template, document = sent[0]
    assert mobile == "9876543210" and template == "ebill"
    assert params[0] == store.name and params[1] == bill["bill_number"] and params[3].startswith("₹")
    assert document == (f"media-Bill-{bill['bill_number']}.pdf", f"Bill-{bill['bill_number']}.pdf")

    receipt = client.get(f"/api/v1/sales/{bill['id']}/receipt", headers=cashier_headers).get_json()
    assert receipt["ebill"]["status"] == "sent" and receipt["ebill"]["recipient"] == "98XXXXX210"


def test_no_ebill_without_mobile_or_when_switched_off(client, admin_headers, cashier_headers, shift, store, sent):
    _paid_bill(client, cashier_headers, store)  # setting off (default)
    _enable(client, admin_headers)
    bill = _paid_bill(client, cashier_headers, store, mobile=None)
    assert sent == [] and _logs() == []
    assert client.get(f"/api/v1/sales/{bill['id']}/receipt", headers=cashier_headers).get_json()["ebill"] is None


def test_same_customer_two_bills_same_day(client, admin_headers, cashier_headers, shift, store, sent):
    _enable(client, admin_headers)
    _paid_bill(client, cashier_headers, store)
    _paid_bill(client, cashier_headers, store)
    assert len(sent) == 2 and [log.status.value for log in _logs()] == ["sent", "sent"]


def test_failed_ebill_is_retried_three_times(client, admin_headers, cashier_headers, shift, store, monkeypatch):
    _enable(client, admin_headers)

    def offline(*args, **kwargs):
        raise whatsapp_gateway.AppError("Cannot reach WhatsApp. Check the internet connection.")

    monkeypatch.setattr(whatsapp_gateway, "upload_media", offline)
    bill = _paid_bill(client, cashier_headers, store)  # checkout still succeeds
    assert _logs()[0].status.value == "failed" and _logs()[0].attempts == 1

    ebill_service.retry_due()
    ebill_service.retry_due()
    assert ebill_service.retry_due() == []  # 3 tries used up
    assert _logs()[0].attempts == 3

    monkeypatch.setattr(whatsapp_gateway, "upload_media", lambda data, filename: "media-1")
    monkeypatch.setattr(whatsapp_gateway, "send_template", lambda *a, **k: "wamid.2")
    resp = client.post(f"/api/v1/sales/{bill['id']}/ebill", json={}, headers=cashier_headers)  # button still works
    assert resp.status_code == 200 and resp.get_json()["status"] == "sent"


def test_retry_sends_after_internet_is_back(client, admin_headers, cashier_headers, shift, store, monkeypatch):
    _enable(client, admin_headers)
    monkeypatch.setattr(whatsapp_gateway, "upload_media", lambda *a: (_ for _ in ()).throw(whatsapp_gateway.AppError("offline")))
    _paid_bill(client, cashier_headers, store)
    monkeypatch.setattr(whatsapp_gateway, "upload_media", lambda data, filename: "media-1")
    results = ebill_service.retry_due()
    assert [r.status for r in results] == ["sent"] and ebill_service.retry_due() == []


def test_send_button_to_typed_number(client, cashier_headers, shift, store, sent):
    """Setting off, no mobile on the bill (e.g. printer broken, customer asks for it on WhatsApp)."""
    bill = _paid_bill(client, cashier_headers, store, mobile=None)
    url = f"/api/v1/sales/{bill['id']}/ebill"

    assert client.post(url, json={}, headers=cashier_headers).status_code == 400  # no number anywhere
    assert client.post(url, json={"mobile": "12345"}, headers=cashier_headers).status_code == 400

    resp = client.post(url, json={"mobile": "+91 91234 56789"}, headers=cashier_headers)
    assert resp.status_code == 200 and resp.get_json() == {**resp.get_json(), "status": "sent", "recipient": "91XXXXX789"}
    assert sent[0][0] == "9123456789"
    # The bill's customer isn't changed (loyalty points stay with whoever was on the bill).
    assert db.session.get(Sale, bill["id"]).customer_mobile is None

    client.post(url, json={"mobile": "9123456789"}, headers=cashier_headers)  # sending again is allowed
    assert len(sent) == 2 and len(_logs()) == 1


def test_send_button_only_for_paid_bills(client, cashier_headers, shift, store):
    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    assert client.post(f"/api/v1/sales/{sid}/ebill", json={"mobile": "9876543210"}, headers=cashier_headers).status_code == 400
