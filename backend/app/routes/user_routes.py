"""User management endpoints (admin only)."""
from flask import Blueprint, jsonify, request

from app.schemas.auth_schemas import UserOut
from app.schemas.common import PagedResponse, PaginationQuery
from app.schemas.user_schemas import PinReset, UserCreate, UserUpdate
from app.services import auth_service, user_service
from app.utils.permissions import require_permission
from app.errors.exceptions import NotFoundError
from app.utils.store_scope import is_head_office, scoped_store_id

user_bp = Blueprint("users", __name__)


@user_bp.get("/users")
@require_permission("users.read")
def list_users():
    q = PaginationQuery.model_validate(request.args)
    store_id = scoped_store_id(auth_service.current_user(), request.args.get("store_id", type=int))
    items, total = user_service.list_users(q.page, q.per_page, q.is_active, store_id)
    resp = PagedResponse.build(
        [UserOut.model_validate(u).model_dump(mode="json") for u in items],
        total, q.page, q.per_page,
    )
    return jsonify(resp.model_dump()), 200


@user_bp.post("/users")
@require_permission("users.create")
def create_user():
    data = UserCreate.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    user = user_service.create_user(data, actor)
    return jsonify(UserOut.model_validate(user).model_dump(mode="json")), 201


@user_bp.get("/users/<int:user_id>")
@require_permission("users.read")
def get_user(user_id: int):
    user = user_service.get_user(user_id)
    actor = auth_service.current_user()
    if not is_head_office(actor) and user.store_id != actor.store_id:
        raise NotFoundError(f"User {user_id} not found.")  # another store's staff are not visible
    return jsonify(UserOut.model_validate(user).model_dump(mode="json")), 200


@user_bp.put("/users/<int:user_id>")
@require_permission("users.update")
def update_user(user_id: int):
    data = UserUpdate.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    user = user_service.update_user(user_id, data, actor)
    return jsonify(UserOut.model_validate(user).model_dump(mode="json")), 200


@user_bp.post("/users/<int:user_id>/reset-pin")
@require_permission("users.update")
def reset_pin(user_id: int):
    data = PinReset.model_validate(request.get_json(force=True))
    actor = auth_service.current_user()
    user_service.reset_pin(user_id, data, actor)
    return jsonify({"message": "PIN reset successfully."}), 200
