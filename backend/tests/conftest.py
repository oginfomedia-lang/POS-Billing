"""Pytest fixtures: test app, database setup, and reusable objects."""
import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    application = create_app("testing")
    ctx = application.app_context()
    ctx.push()
    _db.create_all()
    yield application
    _db.drop_all()
    ctx.pop()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_db(app):
    yield
    _db.session.rollback()
    for table in reversed(_db.metadata.sorted_tables):
        _db.session.execute(table.delete())
    _db.session.commit()


# ── Reusable DB objects ────────────────────────────────────────────────────────

@pytest.fixture
def store(app):
    from tests.factories import make_store
    return make_store()


@pytest.fixture
def admin_user(app, store):
    from tests.factories import make_user
    return make_user(role="admin", username="admin", pin="1234", store=store)


@pytest.fixture
def cashier_user(app, store):
    from tests.factories import make_user
    return make_user(role="cashier", username="cashier1", pin="5678", store=store)


@pytest.fixture
def admin_headers(client, admin_user):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": admin_user.username, "pin": "1234"},
    )
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def cashier_headers(client, cashier_user):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": cashier_user.username, "pin": "5678"},
    )
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
