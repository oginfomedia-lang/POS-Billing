"""Store and counter endpoints."""
from flask import Blueprint, jsonify, request

from app.schemas.common import PagedResponse, PaginationQuery
from app.schemas.store_schemas import CounterCreate, CounterOut, CounterUpdate, StoreCreate, StoreOut, StoreUpdate
from app.services import auth_service, store_service
from app.utils.permissions import require_permission
from app.utils.store_scope import require_store_access, scoped_store_id

store_bp = Blueprint("stores", __name__)


@store_bp.get("/stores")
@require_permission("stores.read")
def list_stores():
    q = PaginationQuery.model_validate(request.args)
    only = scoped_store_id(auth_service.current_user(), None)  # None = all stores (admins)
    items, total = store_service.list_stores(q.page, q.per_page, only)
    resp = PagedResponse.build(
        [StoreOut.model_validate(s).model_dump(mode="json") for s in items],
        total, q.page, q.per_page,
    )
    return jsonify(resp.model_dump()), 200


@store_bp.post("/stores")
@require_permission("stores.create")
def create_store():
    data = StoreCreate.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    store = store_service.create_store(data, actor)
    return jsonify(StoreOut.model_validate(store).model_dump(mode="json")), 201


@store_bp.get("/stores/<int:store_id>")
@require_permission("stores.read")
def get_store(store_id: int):
    require_store_access(auth_service.current_user(), store_id)
    store = store_service.get_store(store_id)
    return jsonify(StoreOut.model_validate(store).model_dump(mode="json")), 200


@store_bp.put("/stores/<int:store_id>")
@require_permission("stores.update")
def update_store(store_id: int):
    data = StoreUpdate.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    store = store_service.update_store(store_id, data, actor)
    return jsonify(StoreOut.model_validate(store).model_dump(mode="json")), 200


@store_bp.get("/stores/<int:store_id>/counters")
@require_permission("counters.read")
def list_counters(store_id: int):
    require_store_access(auth_service.current_user(), store_id)
    counters = store_service.list_counters(store_id)
    return jsonify([CounterOut.model_validate(c).model_dump(mode="json") for c in counters]), 200


@store_bp.post("/stores/<int:store_id>/counters")
@require_permission("counters.create")
def create_counter(store_id: int):
    data = CounterCreate.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    require_store_access(actor, store_id)
    counter = store_service.create_counter(store_id, data, actor)
    return jsonify(CounterOut.model_validate(counter).model_dump(mode="json")), 201


@store_bp.get("/stores/<int:store_id>/counters/<int:counter_id>")
@require_permission("counters.read")
def get_counter(store_id: int, counter_id: int):
    require_store_access(auth_service.current_user(), store_id)
    counter = store_service.get_counter(store_id, counter_id)
    return jsonify(CounterOut.model_validate(counter).model_dump(mode="json")), 200


@store_bp.put("/stores/<int:store_id>/counters/<int:counter_id>")
@require_permission("counters.update")
def update_counter(store_id: int, counter_id: int):
    data = CounterUpdate.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    require_store_access(actor, store_id)
    counter = store_service.update_counter(store_id, counter_id, data, actor)
    return jsonify(CounterOut.model_validate(counter).model_dump(mode="json")), 200
