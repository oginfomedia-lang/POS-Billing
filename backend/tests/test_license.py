"""Shop licence: key validation, activation endpoints and the LICENSE_REQUIRED request check."""
import base64
import hashlib
import hmac
import json
from datetime import date, timedelta

import pytest

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
