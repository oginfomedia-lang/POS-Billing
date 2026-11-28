"""Shop licence: key validation, activation endpoints and the LICENSE_REQUIRED request check."""
import base64
import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services import license_service


def make_key(mid=None, exp=None, secret=license_service.SECRET):
    payload = {
        "product": "LiteRetail",
        "customer": "Test Mart",
        "mid": mid or license_service.machine_id(),
        "iat": date.today().isoformat(),
        "exp": exp or (date.today() + timedelta(days=100)).isoformat(),
    }
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return b64 + "." + hmac.new(secret, b64.encode(), hashlib.sha256).hexdigest()[:32]


@pytest.fixture(autouse=True)
def license_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(license_service, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(license_service, "_cache", None)
    return tmp_path


def test_valid_key():
    status = license_service.validate(make_key())
    assert status.valid and status.customer_name == "Test Mart"
    assert 99 <= status.days_left <= 100


@pytest.mark.parametrize("key, reason", [
    ("", "not_activated"),
    ("no-dot", "invalid_key"),
    (make_key(secret=b"other"), "invalid_key"),
    (make_key(mid="0000000000000000"), "wrong_machine"),
    (make_key(exp="2020-01-01"), "expired"),
])
def test_rejected_keys(key, reason):
    assert license_service.validate(key).reason == reason


def test_machine_id_is_16_hex():
    mid = license_service.machine_id()
    assert len(mid) == 16 and int(mid, 16) >= 0


def test_activate_saves_key_for_the_shop(client, license_dir):
    first = client.get("/api/v1/license").get_json()
    assert first["reason"] == "not_activated" and first["required"] is False

    bad = client.post("/api/v1/license/activate", json={"key": make_key(mid="0000000000000000")})
    assert bad.status_code == 400
    assert bad.get_json()["error"]["code"] == "LICENSE_WRONG_MACHINE"
    assert not (license_dir / "license.json").exists()

    ok = client.post("/api/v1/license/activate", json={"key": make_key()})
    assert ok.status_code == 200 and ok.get_json()["valid"] is True
    assert client.get("/api/v1/license").get_json()["valid"] is True


def test_api_blocked_until_licensed(app, client, admin_user):
    app.config["LICENSE_REQUIRED"] = True
    try:
        login = {"username": "admin", "pin": "1234"}
        blocked = client.post("/api/v1/auth/login", json=login)
        assert blocked.status_code == 403
        assert blocked.get_json()["error"]["code"] == "LICENSE_REQUIRED"
        assert client.get("/api/v1/license").status_code == 200

        client.post("/api/v1/license/activate", json={"key": make_key()})
        assert client.post("/api/v1/auth/login", json=login).status_code == 200
    finally:
        app.config["LICENSE_REQUIRED"] = False


# ── v2 keys (Ed25519) and plans ────────────────────────────────────────────────

_TEST_SIGNER = Ed25519PrivateKey.generate()


@pytest.fixture(autouse=True)
def test_public_key(monkeypatch):
    """The app trusts this test key pair's public half instead of the real one."""
    der = _TEST_SIGNER.public_key().public_bytes(serialization.Encoding.DER,
                                                 serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setattr(license_service, "PUBLIC_KEY_B64", base64.b64encode(der).decode())


def make_v2_key(signer=None, **overrides):
    payload = {"v": 2, "product": "LiteRetail", "customer": "Test Mart", "mid": license_service.machine_id(),
               "plan": "starter", "features": [], "limits": {"counters": 1, "stores": 1, "users": 2},
               "iat": date.today().isoformat(), "exp": None, "amc_until": None, **overrides}
    b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    sig = (signer or _TEST_SIGNER).sign(b64.encode())
    return b64 + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


def test_v2_perpetual_key():
    status = license_service.validate(make_v2_key(features=["purchases", "not_a_feature"]))
    assert status.valid and status.key_version == 2 and status.plan == "starter"
    assert status.days_left is None
    assert status.features == frozenset({"purchases"})
    assert status.limits == {"counters": 1, "stores": 1, "users": 2}


def test_v2_rejected_keys():
    tampered = make_v2_key()
    payload_b64, _, sig = tampered.rpartition(".")
    other_payload = base64.urlsafe_b64encode(b'{"plan":"enterprise"}').decode().rstrip("=")
    assert license_service.validate(f"{other_payload}.{sig}").reason == "invalid_key"
    assert license_service.validate(make_v2_key(signer=Ed25519PrivateKey.generate())).reason == "invalid_key"
    assert license_service.validate(make_v2_key(mid="0000000000000000")).reason == "wrong_machine"
    assert license_service.validate(make_v2_key(exp="2020-01-01")).reason == "expired"


def test_v1_key_keeps_every_feature():
    status = license_service.validate(make_key())
    assert status.key_version == 1 and status.plan == "enterprise"
    assert status.features == license_service.ALL_FEATURES and status.limits is None


def test_v1_keys_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(license_service, "ACCEPT_V1_KEYS", False)
    assert license_service.validate(make_key()).reason == "invalid_key"


def test_plan_blocks_features_and_limits(app, client, admin_headers, store):
    app.config["LICENSE_REQUIRED"] = True
    try:
        assert client.post("/api/v1/license/activate", json={"key": make_v2_key()}).status_code == 200

        blocked = client.get("/api/v1/suppliers", headers=admin_headers)
        assert blocked.status_code == 403
        assert blocked.get_json()["error"]["code"] == "FEATURE_NOT_IN_PLAN"
        assert client.get("/api/v1/stores", headers=admin_headers).status_code == 200

        def new_user(name):
            return client.post("/api/v1/users", headers=admin_headers, json={
                "username": name, "full_name": name, "pin": "4321", "role": "cashier", "store_id": store.id})

        assert new_user("cashier_one").status_code == 201        # 2 of 2 users
        full = new_user("cashier_two")
        assert full.status_code == 403 and full.get_json()["error"]["code"] == "PLAN_LIMIT_REACHED"

        client.post("/api/v1/license/activate", json={"key": make_v2_key(features=["purchases"])})
        assert client.get("/api/v1/suppliers", headers=admin_headers).status_code == 200
    finally:
        app.config["LICENSE_REQUIRED"] = False


def test_starter_plan_switches_off_add_ons(app, client, admin_headers, store):
    """Card/UPI through Razorpay, rewards / customer mobile, e-bill resend, daily report and VPS backups are
    blocked for a plan without them; card/UPI falls back to manual and scale stickers are not read offline."""
    app.config["LICENSE_REQUIRED"] = True
    try:
        client.post("/api/v1/license/activate", json={"key": make_v2_key(limits={})})

        mode = client.get("/api/v1/sales/payment-mode", headers=admin_headers)
        assert mode.status_code == 200 and mode.get_json()["card_upi_mode"] == "manual"

        for method, url in [
            ("post", "/api/v1/sales/1/payment-intents"),
            ("put", "/api/v1/sales/1/customer-mobile"),
            ("post", "/api/v1/sales/1/redeem-points"),
            ("post", "/api/v1/sales/1/ebill"),
            ("post", "/api/v1/settings/daily-report/send"),
            ("post", "/api/v1/backups/1/upload"),
            ("get", "/api/v1/backups/replication"),
        ]:
            resp = getattr(client, method)(url, headers=admin_headers, json={})
            assert resp.status_code == 403, url
            assert resp.get_json()["error"]["code"] == "FEATURE_NOT_IN_PLAN", url

        catalog = client.get(f"/api/v1/pos/offline-catalog?store_id={store.id}", headers=admin_headers)
        assert catalog.status_code == 200 and catalog.get_json()["settings"]["scale_prefix"] == "-"
    finally:
        app.config["LICENSE_REQUIRED"] = False
