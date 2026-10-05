"""User management endpoint tests."""


def test_list_users_admin(client, admin_user, admin_headers):
    resp = client.get("/api/v1/users", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] >= 1
    assert any(u["username"] == "admin" for u in data["items"])


def test_list_users_cashier_forbidden(client, cashier_user, cashier_headers):
    resp = client.get("/api/v1/users", headers=cashier_headers)
    assert resp.status_code == 403


def test_create_user(client, admin_user, admin_headers):
    resp = client.post(
        "/api/v1/users",
        json={"username": "newcashier", "full_name": "New Cashier", "pin": "1111", "role": "cashier"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["username"] == "newcashier"
    assert data["role"] == "cashier"


def test_create_user_duplicate_username(client, admin_user, admin_headers):
    resp = client.post(
        "/api/v1/users",
        json={"username": "admin", "full_name": "Dup", "pin": "1111", "role": "cashier"},
        headers=admin_headers,
    )
    assert resp.status_code == 409


def test_get_user(client, admin_user, admin_headers):
    resp = client.get(f"/api/v1/users/{admin_user.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.get_json()["id"] == admin_user.id


def test_get_user_not_found(client, admin_headers):
    resp = client.get("/api/v1/users/99999", headers=admin_headers)
    assert resp.status_code == 404


def test_update_user(client, admin_user, admin_headers, cashier_user):
    resp = client.put(
        f"/api/v1/users/{cashier_user.id}",
        json={"full_name": "Updated Name", "is_active": False},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["full_name"] == "Updated Name"
    assert data["is_active"] is False


def test_reset_pin(client, admin_user, admin_headers, cashier_user):
    resp = client.post(
        f"/api/v1/users/{cashier_user.id}/reset-pin",
        json={"new_pin": "9876"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    # Verify new PIN works
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": cashier_user.username, "pin": "9876"},
    )
    assert login_resp.status_code == 200
