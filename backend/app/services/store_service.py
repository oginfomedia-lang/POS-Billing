"""Store and counter management (all mutations are audited)."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from app.errors.exceptions import ConflictError, NotFoundError
from app.extensions import db
from app.models.store import Counter, Store
from app.models.user import User
from app.repositories.store_repository import CounterRepository, StoreRepository
from app.schemas.store_schemas import CounterCreate, CounterUpdate, StoreCreate, StoreUpdate
from app.services import audit_service
from app.utils.transactions import transaction


def create_store(data: StoreCreate, actor: User) -> Store:
    store = Store(
        name=data.name,
        address=data.address,
        phone=data.phone,
        gstin=data.gstin,
    )
    with transaction():
        StoreRepository().add(store)
        db.session.flush()
        audit_service.log(actor, "store.create", "store", store.id, None, _store_snap(store))
    return store


def update_store(store_id: int, data: StoreUpdate, actor: User) -> Store:
    store = _get_store_or_404(store_id)
    old = _store_snap(store)

    if data.name is not None:
        store.name = data.name
    if data.address is not None:
        store.address = data.address
    if data.phone is not None:
        store.phone = data.phone
    if data.gstin is not None:
        store.gstin = data.gstin
    if data.is_active is not None:
        store.is_active = data.is_active

    with transaction():
        audit_service.log(actor, "store.update", "store", store.id, old, _store_snap(store))
    return store


def get_store(store_id: int) -> Store:
    return _get_store_or_404(store_id)


def list_stores(page: int, per_page: int, only_store_id: int | None = None) -> tuple[list[Store], int]:
    """All stores, or just one (a branch user only sees their own store)."""
    return StoreRepository().list(page=page, per_page=per_page, store_id=only_store_id)


def create_counter(store_id: int, data: CounterCreate, actor: User) -> Counter:
    store = _get_store_or_404(store_id)
    label = data.label.strip()
    _check_counter_free(store, data.code, label)

    counter = Counter(
        code=data.code,
        label=label,
        store_id=store_id,
        edc_device_id=(data.edc_device_id or "").strip() or None,
    )
    try:
        with transaction():
            CounterRepository().add(counter)
            db.session.flush()
            audit_service.log(actor, "counter.create", "counter", counter.id, None, _counter_snap(counter))
    except IntegrityError:  # another admin saved the same code / label a moment ago
        raise ConflictError(f"Counter '{data.code}' / '{label}' already exists in {store.name}.") from None
    return counter


def update_counter(store_id: int, counter_id: int, data: CounterUpdate, actor: User) -> Counter:
    counter = _get_counter_or_404(store_id, counter_id)
    old = _counter_snap(counter)

    if data.label is not None and data.label.strip() != counter.label:
        _check_counter_free(counter.store, None, data.label.strip(), exclude_id=counter.id)
        counter.label = data.label.strip()
    if data.is_active is not None:
        counter.is_active = data.is_active
    if data.edc_device_id is not None:                                  
        counter.edc_device_id = data.edc_device_id.strip() or None 

    try:
        with transaction():
            audit_service.log(actor, "counter.update", "counter", counter.id, old, _counter_snap(counter))
    except IntegrityError:
        raise ConflictError(f"A counter named '{counter.label}' already exists in this store.") from None
    return counter


def get_counter(store_id: int, counter_id: int) -> Counter:
    return _get_counter_or_404(store_id, counter_id)


def list_counters(store_id: int) -> list[Counter]:
    _get_store_or_404(store_id)
    return CounterRepository().list_for_store(store_id)


def _check_counter_free(store: Store, code: str | None, label: str, exclude_id: int | None = None) -> None:
    """Code and name are unique within the store; other stores may use the same ones."""
    repo = CounterRepository()
    if code is not None and repo.get_by_code(store.id, code) is not None:
        raise ConflictError(f"Counter code '{code}' already exists in {store.name}.")
    same = repo.get_by_label_ci(store.id, label)
    if same is not None and same.id != exclude_id:
        raise ConflictError(f"A counter named '{label}' already exists in {store.name} (code {same.code}).")


def _get_store_or_404(store_id: int) -> Store:
    store = StoreRepository().get_by_id(store_id)
    if store is None:
        raise NotFoundError(f"Store {store_id} not found.")
    return store


def _get_counter_or_404(store_id: int, counter_id: int) -> Counter:
    counter = CounterRepository().get_by_id(counter_id)
    if counter is None or counter.store_id != store_id:
        raise NotFoundError(f"Counter {counter_id} not found in store {store_id}.")
    return counter


def _store_snap(s: Store) -> dict:
    return {"name": s.name, "address": s.address, "phone": s.phone, "gstin": s.gstin, "is_active": s.is_active}


def _counter_snap(c: Counter) -> dict:
    return {"code": c.code, "label": c.label, "store_id": c.store_id, "is_active": c.is_active, "edc_device_id": c.edc_device_id,}
