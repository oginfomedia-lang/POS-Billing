"""flask create-admin command."""
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User


def _run(app, *args, input=None):
    return app.test_cli_runner().invoke(args=["create-admin", *args], input=input)


def test_create_admin_and_login(app, client):
    result = _run(app, "--username", "owner", "--full-name", "Store Owner", input="4321\n4321\n")
    assert result.exit_code == 0, result.output
    user = db.session.scalar(db.select(User).where(User.username == "owner"))
    assert user.role is UserRole.ADMIN
    assert client.post("/api/v1/auth/login", json={"username": "owner", "pin": "4321"}).status_code == 200
    entry = db.session.scalar(db.select(AuditLog).where(AuditLog.action == "user.create"))
    assert entry.user_id is None and entry.new_values["username"] == "owner"


def test_create_admin_pin_mismatch(app):
    result = _run(app, "--username", "owner", "--full-name", "Owner", input="4321\n9999\n4321\n4321\n")
    assert result.exit_code == 0  # click re-prompts until both entries match
    assert db.session.scalar(db.select(User).where(User.username == "owner")) is not None


def test_create_admin_rejects_duplicate_and_bad_input(app, admin_user):
    dup = _run(app, "--username", "admin", "--full-name", "X", "--pin", "1234")
    assert dup.exit_code != 0 and "already taken" in dup.output

    bad = _run(app, "--username", "Bad Name", "--full-name", "X", "--pin", "12")
    assert bad.exit_code != 0 and "username" in bad.output and "pin" in bad.output

    no_store = _run(app, "--username", "owner2", "--full-name", "X", "--pin", "1234", "--store-id", "99999")
    assert no_store.exit_code != 0 and "Store 99999 does not exist" in no_store.output
