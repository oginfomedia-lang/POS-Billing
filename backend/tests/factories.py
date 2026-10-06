"""Helpers to create test users, products, stock and sales."""
import uuid
from decimal import Decimal

from app.extensions import db
from app.models.enums import ShiftStatus
from app.models.inventory import Inventory
from app.models.product import Product, ProductBarcode
from app.models.shift import CashierShift
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


def make_product(
    store: Store,
    name: str = "Test Product",
    price: str = "10.00",
    gst_rate: str = "5.00",
    stock: int = 100,
    barcode: str | None = None,
) -> Product:
    product = Product(name=name, selling_price=Decimal(price), gst_rate=Decimal(gst_rate))
    product.barcodes.append(ProductBarcode(barcode=barcode or uuid.uuid4().hex[:13]))
    db.session.add(product)
    db.session.flush()
    db.session.add(Inventory(store_id=store.id, product_id=product.id, qty_on_hand=stock))
    db.session.commit()
    return product


def make_shift(user: User, counter: Counter, opening_cash: str = "0.00") -> CashierShift:
    shift = CashierShift(
        store_id=counter.store_id,
        counter_id=counter.id,
        cashier_id=user.id,
        status=ShiftStatus.OPEN,
        opening_cash=Decimal(opening_cash),
    )
    db.session.add(shift)
    db.session.commit()
    return shift
