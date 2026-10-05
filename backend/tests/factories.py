"""Helpers to create test users, products, stock and sales."""
import uuid

from app.extensions import db
from app.models.store import Counter, Store
from app.models.user import User
from app.utils.security import hash_pin


def make_store(name: str = "Test Store", **kwargs) -> Store:
    store = Store(name=name, address="1 Test Rd", **kwargs)
    db.session.add(store)
    db.session.commit()
    return store


def make_counter(store: Store, code: str = "C01", label: str = "Counter 1", **kwargs) -> Counter:
    counter = Counter(code=code, label=label, store_id=store.id, **kwargs)
    db.session.add(counter)
    db.session.commit()
    return counter


def make_user(
    role: str = "cashier",
    username: str | None = None,
    pin: str = "1234",
    store: Store | None = None,
    **kwargs,
) -> User:
    if username is None:
        username = f"user_{uuid.uuid4().hex[:8]}"
    user = User(
        username=username,
        full_name="Test User",
        pin_hash=hash_pin(pin),
        role=role,
        store_id=store.id if store else None,
        **kwargs,
    )
    db.session.add(user)
    db.session.commit()
    return user
