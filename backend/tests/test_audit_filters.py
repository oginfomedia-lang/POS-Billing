"""Audit log filters: by role or person, by part of the action, by record type, and any combination."""
from app.extensions import db
from app.models.audit_log import AuditLog
from tests.factories import make_user


def _log(user, action, entity_type):
    db.session.add(AuditLog(user_id=user.id if user else None, username=user.username if user else None,
                            action=action, entity_type=entity_type, entity_id="1"))
    db.session.commit()


def _actions(client, headers, **params):
    resp = client.get("/api/v1/audit-logs", query_string=params, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return sorted(((i["username"], i["action"]) for i in resp.get_json()["items"]), key=lambda r: (r[0] or "", r[1]))


def _setup(admin_user, store):
    mgr = make_user(role="manager", username="mgr_rahul", pin="2468", store=store)
    cash = make_user(role="cashier", username="till1", pin="2468", store=store)
    mgr.full_name, cash.full_name = "Rahul Patil", "Sita"
    db.session.commit()
    _log(admin_user, "product.create", "product")
    _log(admin_user, "user.create", "user")
    _log(mgr, "sale.void", "sale")
    _log(mgr, "category.update", "category")
    _log(cash, "sale.complete", "sale")
    _log(None, "backup.create", "backup")  # from the command line: no user


def test_filter_by_role(client, admin_headers, admin_user, store):
    _setup(admin_user, store)
    assert _actions(client, admin_headers, user="admin") == [("admin", "product.create"), ("admin", "user.create")]
    assert _actions(client, admin_headers, user="Manager") == [("mgr_rahul", "category.update"), ("mgr_rahul", "sale.void")]
    assert _actions(client, admin_headers, user="cashiers") == [("till1", "sale.complete")]


def test_filter_by_part_of_username_or_full_name(client, admin_headers, admin_user, store):
    _setup(admin_user, store)
    by_username = _actions(client, admin_headers, user="mgr")
    assert by_username == _actions(client, admin_headers, user="rahul")  # full name "Rahul Patil"
    assert len(by_username) == 2
    assert _actions(client, admin_headers, user="nobody") == []


def test_action_matches_any_part(client, admin_headers, admin_user, store):
    _setup(admin_user, store)
    assert _actions(client, admin_headers, action="sale") == [("mgr_rahul", "sale.void"), ("till1", "sale.complete")]
    assert _actions(client, admin_headers, action="CREATE") == [
        (None, "backup.create"), ("admin", "product.create"), ("admin", "user.create")]
    assert _actions(client, admin_headers, action="%") == []  # typed literally, not a wildcard


def test_filters_combine(client, admin_headers, admin_user, store):
    _setup(admin_user, store)
    assert _actions(client, admin_headers, user="admin", action="create") == [
        ("admin", "product.create"), ("admin", "user.create")]
    assert _actions(client, admin_headers, user="admin", action="product") == [("admin", "product.create")]
    assert _actions(client, admin_headers, user="manager", action="sale") == [("mgr_rahul", "sale.void")]
    assert _actions(client, admin_headers, user="admin", action="sale") == []
    assert _actions(client, admin_headers, user="manager", entity_type="sale") == [("mgr_rahul", "sale.void")]


def test_filter_suggestions(client, admin_headers, admin_user, store):
    _setup(admin_user, store)
    values = client.get("/api/v1/audit-logs/filters", headers=admin_headers).get_json()
    assert values["roles"] == ["admin", "manager", "cashier"]
    assert "sale.complete" in values["actions"] and "backup.create" in values["actions"]
    assert values["entity_types"] == ["backup", "category", "product", "sale", "user"]
    assert {"username": "mgr_rahul", "full_name": "Rahul Patil", "role": "manager"} in values["users"]


def test_cashier_cannot_read_audit_logs(client, cashier_headers):
    assert client.get("/api/v1/audit-logs/filters", headers=cashier_headers).status_code == 403
