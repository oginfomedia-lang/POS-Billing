"""Settings → Integrations: Razorpay / Paytm / WhatsApp details entered in the app instead of .env."""
import json

import pytest

from app.extensions import db
from app.models.system import SystemSetting
from app.services import integration_settings_service
from tests.factories import make_user

pytestmark = pytest.mark.integration

URL = "/api/v1/settings/integrations"


@pytest.fixture
def manager_headers(client, store):
    make_user(role="manager", username="mgr", pin="4321", store=store)
    token = client.post("/api/v1/auth/login", json={"username": "mgr", "pin": "4321"}).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _stored(name):
    db.session.expire_all()
    row = db.session.get(SystemSetting, "int." + name.lower())
    return row.value if row else None


def test_secret_is_encrypted_and_never_sent_back(client, app, admin_headers):
    resp = client.put(URL, json={"RAZORPAY_KEY_ID": "rzp_test_abc", "RAZORPAY_KEY_SECRET": "very-secret-123"},
                      headers=admin_headers)
    assert resp.status_code == 200, resp.get_json()

    stored = _stored("RAZORPAY_KEY_SECRET")
    assert stored.startswith("enc:") and "very-secret-123" not in stored
    assert _stored("RAZORPAY_KEY_ID") == "rzp_test_abc"  # not a secret: kept readable

    body = client.get(URL, headers=admin_headers).get_json()
    assert "very-secret-123" not in json.dumps(body)
    assert body["razorpay"]["RAZORPAY_KEY_SECRET"] == {"set": True, "unreadable": False, "from_env": False}
    assert body["razorpay"]["RAZORPAY_KEY_ID"] == {"value": "rzp_test_abc", "from_env": False}

    with app.test_request_context():
        assert integration_settings_service.value("RAZORPAY_KEY_SECRET") == "very-secret-123"
        assert integration_settings_service.value("RAZORPAY_KEY_ID") == "rzp_test_abc"


def test_keep_clear_and_env_fallback(client, app, admin_headers):
    client.put(URL, json={"WHATSAPP_TOKEN": "tok-1", "WHATSAPP_PHONE_NUMBER_ID": "111"}, headers=admin_headers)
    # Saving other fields without the token (or with null) keeps it.
    client.put(URL, json={"WHATSAPP_TOKEN": None, "WHATSAPP_TEMPLATE_LANG": "mr"}, headers=admin_headers)
    with app.test_request_context():
        assert integration_settings_service.value("WHATSAPP_TOKEN") == "tok-1"
        assert integration_settings_service.value("WHATSAPP_TEMPLATE_LANG") == "mr"

    # "" removes the app value: back to the .env / config value.
    client.put(URL, json={"WHATSAPP_TOKEN": "", "WHATSAPP_TEMPLATE_LANG": ""}, headers=admin_headers)
    assert _stored("WHATSAPP_TOKEN") is None
    body = client.get(URL, headers=admin_headers).get_json()["whatsapp"]
    assert body["WHATSAPP_TEMPLATE_LANG"] == {"value": "en", "from_env": True}
    with app.test_request_context():
        assert integration_settings_service.value("WHATSAPP_TOKEN") == app.config["WHATSAPP_TOKEN"]


def test_numbers_and_switches(client, app, admin_headers):
    resp = client.put(URL, json={"UPI_QR_EXPIRY_SECONDS": 600, "PAYTM_MID": "MID123", "RAZORPAY_MOCK": False},
                      headers=admin_headers)
    assert resp.status_code == 200
    with app.test_request_context():
        assert integration_settings_service.value("UPI_QR_EXPIRY_SECONDS") == 600
        assert integration_settings_service.value("PAYTM_MID") == "MID123"
        # Saved as off, but tests can never move real money.
        assert integration_settings_service.value("RAZORPAY_MOCK") is True
    assert _stored("RAZORPAY_MOCK") == "0"


def test_bad_values_are_refused(client, admin_headers):
    assert client.put(URL, json={"RAZORPAY_POS_BASE_URL": "http://insecure"}, headers=admin_headers).status_code == 422
    assert client.put(URL, json={"UPI_QR_EXPIRY_SECONDS": 30}, headers=admin_headers).status_code == 422
    assert client.put(URL, json={"SOMETHING_ELSE": "x"}, headers=admin_headers).status_code == 422


def test_audit_log_names_fields_but_never_values(client, admin_headers):
    client.put(URL, json={"PAYTM_MERCHANT_KEY": "paytm-secret-999", "PAYTM_MID": "M1"}, headers=admin_headers)
    audit = client.get("/api/v1/audit-logs?action=integrations.update", headers=admin_headers).get_json()["items"]
    assert audit[0]["new_values"] == {"changed": ["PAYTM_MERCHANT_KEY", "PAYTM_MID"]}
    assert "paytm-secret-999" not in json.dumps(audit)


def test_unreadable_secret_after_secret_key_change(client, app, admin_headers):
    client.put(URL, json={"RAZORPAY_KEY_SECRET": "abc"}, headers=admin_headers)
    original = app.config["SECRET_KEY"]
    app.config["SECRET_KEY"] = "a-different-secret-key"
    try:
        body = client.get(URL, headers=admin_headers).get_json()["razorpay"]["RAZORPAY_KEY_SECRET"]
        assert body == {"set": False, "unreadable": True, "from_env": False}
    finally:
        app.config["SECRET_KEY"] = original


def test_connection_test_in_test_mode(client, admin_headers):
    for provider in ("razorpay", "whatsapp"):
        resp = client.post(f"{URL}/test/{provider}", headers=admin_headers)
        assert resp.status_code == 200 and "Test mode" in resp.get_json()["message"]
    assert client.post(f"{URL}/test/paytm", headers=admin_headers).status_code == 404


def test_admin_only(client, manager_headers, cashier_headers):
    for headers in (manager_headers, cashier_headers):
        assert client.get(URL, headers=headers).status_code == 403
        assert client.put(URL, json={"PAYTM_MID": "x"}, headers=headers).status_code == 403
        assert client.post(f"{URL}/test/razorpay", headers=headers).status_code == 403
