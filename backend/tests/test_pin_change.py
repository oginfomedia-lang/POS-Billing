"""A PIN set by an admin (or the installer default) must be changed by its owner before they can use the app."""
from tests.factories import make_user


def _login(client, username, pin):
    return client.post("/api/v1/auth/login", json={"username": username, "pin": pin})


def _headers(resp):
    return {"Authorization": f"Bearer {resp.get_json()['access_token']}"}


def _create_cashier(client, admin_headers, store, username="neha", pin="2468"):
    resp = client.post(
        "/api/v1/users",
        json={"username": username, "full_name": "Neha", "pin": pin, "role": "cashier", "store_id": store.id},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.get_json()


def test_new_user_must_change_pin_before_anything_else(client, admin_headers, store):
    _create_cashier(client, admin_headers, store)
    login = _login(client, "neha", "2468")
    assert login.status_code == 200
    assert login.get_json()["user"]["must_change_pin"] is True
    h = _headers(login)

    blocked = client.get("/api/v1/shifts/active", headers=h)
    assert blocked.status_code == 403 and blocked.get_json()["error"]["code"] == "PIN_CHANGE_REQUIRED"
    assert client.get("/api/v1/auth/me", headers=h).status_code == 200  # the screen still knows who it is
    assert client.get("/api/v1/health", headers=h).status_code == 200

    changed = client.post("/api/v1/auth/change-pin", json={"current_pin": "2468", "new_pin": "8642"}, headers=h)
    assert changed.status_code == 200, changed.get_json()
    body = changed.get_json()
    assert body["user"]["must_change_pin"] is False
    new_h = _headers(changed)
    assert client.get("/api/v1/shifts/active", headers=new_h).status_code != 403

    # The old token is gone (session ended); the new PIN works, the admin's doesn't.
    assert client.get("/api/v1/auth/me", headers=h).status_code == 401
    assert _login(client, "neha", "2468").status_code == 401
    assert _login(client, "neha", "8642").get_json()["user"]["must_change_pin"] is False


def test_admin_pin_reset_requires_a_change_again(client, admin_headers, store):
    user = make_user(role="cashier", username="ravi", pin="1111x", store=store)
    assert _login(client, "ravi", "1111x").get_json()["user"]["must_change_pin"] is False
    client.post(f"/api/v1/users/{user.id}/reset-pin", json={"new_pin": "5555x"}, headers=admin_headers)
    assert _login(client, "ravi", "5555x").get_json()["user"]["must_change_pin"] is True


def test_refreshed_token_is_still_limited(client, admin_headers, store):
    _create_cashier(client, admin_headers, store, username="asha")
    login = _login(client, "asha", "2468").get_json()
    refreshed = client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {login['refresh_token']}"})
    h = {"Authorization": f"Bearer {refreshed.get_json()['access_token']}"}
    assert client.get("/api/v1/shifts/active", headers=h).status_code == 403


def test_wrong_current_pin_same_pin_and_weak_pin_are_refused(client, admin_headers, store):
    _create_cashier(client, admin_headers, store, username="sunil")
    h = _headers(_login(client, "sunil", "2468"))
    change = lambda cur, new: client.post("/api/v1/auth/change-pin", json={"current_pin": cur, "new_pin": new}, headers=h)
    assert change("9999", "8642").status_code == 401
    assert change("2468", "2468").status_code == 400
    assert change("2468", "admin123").status_code == 400
    assert change("2468", "12").status_code == 422


def test_anyone_can_change_their_own_pin(client, cashier_user, cashier_headers):
    resp = client.post("/api/v1/auth/change-pin", json={"current_pin": "5678", "new_pin": "7531"}, headers=cashier_headers)
    assert resp.status_code == 200
    assert _login(client, cashier_user.username, "7531").status_code == 200


def test_cli_admin_chose_their_own_pin(app, store):
    from app.models.enums import UserRole
    from app.schemas.user_schemas import UserCreate
    from app.services import user_service

    data = UserCreate(username="owner", full_name="Owner", pin="9182", role=UserRole.ADMIN, store_id=None)
    assert user_service.create_user(data, actor=None, must_change_pin=False).must_change_pin is False
