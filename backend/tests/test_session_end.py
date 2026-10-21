"""An admin's PIN reset (or role / store change, or deactivation) logs the person out of every open session."""
from flask_jwt_extended import create_access_token

from tests.factories import make_store, make_user


def _login(client, username, pin):
    data = client.post("/api/v1/auth/login", json={"username": username, "pin": pin}).get_json()
    return {"Authorization": f"Bearer {data['access_token']}"}, {"Authorization": f"Bearer {data['refresh_token']}"}


def _me(client, headers):
    return client.get("/api/v1/auth/me", headers=headers)


def _refresh(client, refresh_headers):
    return client.post("/api/v1/auth/refresh", headers=refresh_headers)


def test_pin_reset_ends_the_old_session(client, admin_headers, store):
    user = make_user(role="cashier", username="rahul", pin="2468", store=store)
    access, refresh = _login(client, "rahul", "2468")
    assert _me(client, access).status_code == 200

    assert client.post(f"/api/v1/users/{user.id}/reset-pin", json={"new_pin": "1357"},
                       headers=admin_headers).status_code == 200

    old = _me(client, access)
    assert old.status_code == 401 and old.get_json()["error"]["code"] == "SESSION_ENDED"
    assert _refresh(client, refresh).status_code == 401  # can't quietly get a new token either
    assert client.post("/api/v1/sales", headers=access).status_code == 401

    # The new PIN works; the old one doesn't.
    assert client.post("/api/v1/auth/login", json={"username": "rahul", "pin": "2468"}).status_code == 401
    new_access, new_refresh = _login(client, "rahul", "1357")
    assert _me(client, new_access).status_code == 200
    assert _refresh(client, new_refresh).status_code == 200


def test_role_or_store_change_ends_sessions_but_a_new_name_does_not(client, admin_headers, store):
    user = make_user(role="manager", username="mgr", pin="2468", store=store)
    access, _ = _login(client, "mgr", "2468")

    client.put(f"/api/v1/users/{user.id}", json={"full_name": "Manager Saheb"}, headers=admin_headers)
    assert _me(client, access).status_code == 200  # only the name changed

    client.put(f"/api/v1/users/{user.id}", json={"role": "cashier"}, headers=admin_headers)
    assert _me(client, access).status_code == 401  # the old token still said "manager"

    access, _ = _login(client, "mgr", "2468")
    other = make_store(name="Branch 2")
    client.put(f"/api/v1/users/{user.id}", json={"store_id": other.id}, headers=admin_headers)
    assert _me(client, access).status_code == 401


def test_deactivation_ends_sessions_and_reactivation_needs_a_new_login(client, admin_headers, store):
    user = make_user(role="cashier", username="till", pin="2468", store=store)
    access, refresh = _login(client, "till", "2468")
    client.put(f"/api/v1/users/{user.id}", json={"is_active": False}, headers=admin_headers)
    assert _me(client, access).status_code == 401
    client.put(f"/api/v1/users/{user.id}", json={"is_active": True}, headers=admin_headers)
    assert _me(client, access).status_code == 401 and _refresh(client, refresh).status_code == 401
    assert _me(client, _login(client, "till", "2468")[0]).status_code == 200


def test_only_that_users_sessions_end(client, admin_headers, store):
    a = make_user(role="cashier", username="cash_a", pin="2468", store=store)
    make_user(role="cashier", username="cash_b", pin="2468", store=store)
    access_b, _ = _login(client, "cash_b", "2468")
    client.post(f"/api/v1/users/{a.id}/reset-pin", json={"new_pin": "1357"}, headers=admin_headers)
    assert _me(client, access_b).status_code == 200
    assert _me(client, admin_headers).status_code == 200


def test_tokens_from_before_the_upgrade_still_work(app, client, store):
    """Tokens issued before this change have no "sv" claim: they stay valid until the PIN is next reset."""
    user = make_user(role="cashier", username="old_till", pin="2468", store=store)
    legacy = create_access_token(identity=str(user.id), additional_claims={"role": "cashier", "username": "old_till"})
    assert _me(client, {"Authorization": f"Bearer {legacy}"}).status_code == 200
