"""Too many wrong PINs lock that user for a while (login and manager approvals), and API replies carry
hardening headers."""
from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models.user import User
from tests.factories import make_counter, make_product, make_shift, make_user


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _login(client, username, pin):
    return client.post("/api/v1/auth/login", json={"username": username, "pin": pin})


def _approve(client, headers, sid, item, pin, username="mgr"):
    body = {"amount": "1", "reason": "damaged", "approver_username": username, "approver_pin": pin}
    return client.post(f"/api/v1/sales/{sid}/items/{item}/manual-discount", json=body, headers=headers)


def _unlock_clock(username):
    """Pretend the lock time has passed."""
    user = db.session.scalar(db.select(User).filter_by(username=username))
    user.pin_locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.session.commit()


def test_manager_pin_guessing_through_discount_approval_is_stopped(client, cashier_headers, shift, store):
    make_user(role="manager", username="mgr", pin="2468", store=store)
    p = make_product(store, price="10.00")
    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    item = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": p.id}, headers=cashier_headers).get_json()["items"][0]["id"]

    codes = [_approve(client, cashier_headers, sid, item, str(g)).status_code for g in range(3000, 3005)]
    assert codes == [403] * 5
    locked = _approve(client, cashier_headers, sid, item, "2468")  # even the right PIN waits now
    assert locked.status_code == 429 and locked.get_json()["error"]["code"] == "TOO_MANY_ATTEMPTS"
    assert "Too many wrong PINs for 'mgr'" in locked.get_json()["error"]["message"]
    assert _login(client, "mgr", "2468").status_code == 429  # same lock for logging in

    _unlock_clock("mgr")
    assert _approve(client, cashier_headers, sid, item, "2468").status_code == 200


def test_login_brute_force_is_stopped_and_a_success_resets_the_count(client, store):
    make_user(role="cashier", username="till", pin="2468", store=store)
    for _ in range(4):
        assert _login(client, "till", "0000").status_code == 401
    assert _login(client, "till", "2468").status_code == 200  # 4 wrong, then right: count starts again
    for _ in range(4):
        assert _login(client, "till", "0000").status_code == 401
    assert _login(client, "till", "0000").status_code == 401  # 5th wrong in a row locks
    assert _login(client, "till", "2468").status_code == 429


def test_pin_reset_by_admin_lifts_the_lock(client, admin_headers, store):
    user = make_user(role="cashier", username="till", pin="2468", store=store)
    for _ in range(5):
        _login(client, "till", "0000")
    assert _login(client, "till", "2468").status_code == 429
    client.post(f"/api/v1/users/{user.id}/reset-pin", json={"new_pin": "1357"}, headers=admin_headers)
    assert _login(client, "till", "1357").status_code == 200


def test_one_users_lock_does_not_affect_others(client, store):
    make_user(role="cashier", username="till", pin="2468", store=store)
    make_user(role="cashier", username="other", pin="2468", store=store)
    for _ in range(5):
        _login(client, "till", "0000")
    assert _login(client, "other", "2468").status_code == 200


def test_api_replies_carry_hardening_headers(client, admin_headers):
    for resp in (client.get("/api/v1/auth/me", headers=admin_headers), client.get("/api/v1/health"),
                 client.get("/api/v1/users", headers={})):
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Cache-Control"] == "no-store"
        assert resp.headers["X-Frame-Options"] == "DENY"
