"""Create/update/reset-pin for users (all actions are audited)."""
from __future__ import annotations

from app.errors.exceptions import ConflictError, NotFoundError
from app.extensions import db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user_schemas import PinReset, UserCreate, UserUpdate
from app.services import audit_service
from app.utils.security import hash_pin
from app.utils.transactions import transaction


def create_user(data: UserCreate, actor: User) -> User:
    repo = UserRepository()
    if repo.get_by_username(data.username):
        raise ConflictError(f"Username '{data.username}' is already taken.")

    user = User(
        username=data.username,
        full_name=data.full_name,
        pin_hash=hash_pin(data.pin),
        role=data.role,
        store_id=data.store_id,
    )
    with transaction():
        repo.add(user)
        db.session.flush()
        audit_service.log(actor, "user.create", "user", user.id, None, _snap(user))
    return user


def update_user(user_id: int, data: UserUpdate, actor: User) -> User:
    user = _get_or_404(user_id)
    old = _snap(user)

    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.store_id is not None:
        user.store_id = data.store_id
    if data.is_active is not None:
        user.is_active = data.is_active

    with transaction():
        audit_service.log(actor, "user.update", "user", user.id, old, _snap(user))
    return user


def reset_pin(user_id: int, data: PinReset, actor: User) -> User:
    user = _get_or_404(user_id)
    user.pin_hash = hash_pin(data.new_pin)
    with transaction():
        audit_service.log(actor, "user.reset_pin", "user", user.id, None, {"pin_changed": True})
    return user


def get_user(user_id: int) -> User:
    return _get_or_404(user_id)


def list_users(page: int, per_page: int) -> tuple[list[User], int]:
    return UserRepository().list(page=page, per_page=per_page)


def _get_or_404(user_id: int) -> User:
    user = UserRepository().get_by_id(user_id)
    if user is None:
        raise NotFoundError(f"User {user_id} not found.")
    return user


def _snap(user: User) -> dict:
    return {
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role.value,
        "store_id": user.store_id,
        "is_active": user.is_active,
    }
