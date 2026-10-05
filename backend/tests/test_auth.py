"""Auth endpoint tests."""


def test_login_success(client, admin_user):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "pin": "1234"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "admin"


def test_login_wrong_pin(client, admin_user):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "pin": "9999"})
    assert resp.status_code == 401
    assert resp.get_json()["error"]["code"] == "UNAUTHORIZED"


def test_login_unknown_user(client):
    resp = client.post("/api/v1/auth/login", json={"username": "nobody", "pin": "1234"})
    assert resp.status_code == 401


def test_login_inactive_user(client, admin_user):
    from app.extensions import db
    admin_user.is_active = False
    db.session.commit()
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "pin": "1234"})
    assert resp.status_code == 401


def test_me_authenticated(client, admin_user, admin_headers):
    resp = client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.get_json()["username"] == "admin"


def test_me_no_token(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


def test_login_missing_pin(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin"})
    assert resp.status_code == 422
