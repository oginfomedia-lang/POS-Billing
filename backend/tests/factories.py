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


def make_counter(store: Store, code: str = "C01", label: str | None = None, **kwargs) -> Counter:
    # Names are unique per store: default to one per code ("Counter C01").
    counter = Counter(code=code, label=label or f"Counter {code}", store_id=store.id, **kwargs)
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
    tax_rate: str = "5.00",
    stock: int = 100,
    barcode: str | None = None,
    sku: str | None = None,
    is_variable_weight: bool = False,
    mrp: str | None = None,
    hsn_code: str | None = None,
) -> Product:
    unique_sku = sku or f"SKU-{uuid.uuid4().hex[:8]}"
    product = Product(
        sku=unique_sku,
        name=name,
        price=Decimal(price),
        tax_rate=Decimal(tax_rate),
        is_variable_weight=is_variable_weight,
        mrp=Decimal(mrp) if mrp is not None else None,
        hsn_code=hsn_code,
    )
    if barcode:
        product.barcodes.append(ProductBarcode(barcode=barcode, is_primary=True))
    db.session.add(product)
    db.session.flush()
    db.session.add(Inventory(store_id=store.id, product_id=product.id, qty_on_hand=stock))
    db.session.commit()
    return product



def make_shift(user: User, counter: Counter | None = None, opening_float: str = "0.00") -> CashierShift:
    shift = CashierShift(
        store_id=counter.store_id if counter else user.store_id,
        counter_id=counter.id if counter else None,
        user_id=user.id,
        status=ShiftStatus.OPEN,
        opening_float=Decimal(opening_float),
    )
    db.session.add(shift)
    db.session.commit()
    return shift


def pay_by_razorpay(client, headers, sale_id: int, method: str = "upi"):
    """Pays a bill by card/UPI the way the POS does (Razorpay mock mode).

    Starts the payment, pretends the customer paid, then polls once. Returns the poll response:
    on success its JSON has status "paid" and the completed bill under "sale".
    """
    from app.models.payment_intent import PaymentIntent
    from app.services import razorpay_gateway

    resp = client.post(f"/api/v1/sales/{sale_id}/payment-intents", json={"method": method}, headers=headers)
    if resp.status_code != 201:
        return resp
    intent_id = resp.get_json()["id"]
    ref = db.session.get(PaymentIntent, intent_id).provider_ref
    razorpay_gateway._mock_started[ref] = 0  # "paid" long ago
    return client.get(f"/api/v1/payment-intents/{intent_id}", headers=headers)
