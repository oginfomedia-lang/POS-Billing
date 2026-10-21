"""Create/update/reset-pin for users (all actions are audited)."""
from __future__ import annotations

from app.errors.exceptions import BadRequestError, ConflictError, NotFoundError, UnauthorizedError
from app.extensions import db
from app.models.enums import UserRole
from app.models.store import Store
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user_schemas import PinChange, PinReset, UserCreate, UserUpdate
from app.services import audit_service
from app.utils.security import check_user_pin, hash_pin
from app.utils.transactions import transaction


def create_user(data: UserCreate, actor: User | None, must_change_pin: bool = True) -> User:
    """The login (username) is unique across all stores, because staff log in with username + PIN only.
    The full name may repeat: "Rahul" can work at Store A and Store B with logins rahul_a and rahul_b.

    must_change_pin: the person picks their own PIN at first login (the admin who typed this one knows it).
    False only when the person chose the PIN themselves (flask create-admin)."""
    repo = UserRepository()
    taken = repo.get_by_username(data.username)
    if taken:
        where = f" at {taken.store.name}" if taken.store else ""
        raise ConflictError(
            f"Login name '{data.username}' is already taken by {taken.full_name}{where}. "
            "Login names must be unique across all stores; the full name can be the same."
        )
    _check_store(data.role, data.store_id, new=True)

    user = User(
        username=data.username,
        full_name=data.full_name,
        pin_hash=hash_pin(data.pin),
        role=data.role,
        store_id=data.store_id,
        must_change_pin=must_change_pin,
    )
    with transaction():
        repo.add(user)
        db.session.flush()
        audit_service.log(actor, "user.create", "user", user.id, None, _snap(user))
    return user


def update_user(user_id: int, data: UserUpdate, actor: User) -> User:
    user = _get_or_404(user_id)
    old = _snap(user)

    _check_store(data.role or user.role, data.store_id if data.store_id is not None else user.store_id,
                 new=data.store_id is not None and data.store_id != user.store_id)
    if data.full_name is not None:
        user.full_name = data.full_name
    if data.role is not None:
        user.role = data.role
    if data.store_id is not None:
        user.store_id = data.store_id
    if data.is_active is not None:
        user.is_active = data.is_active
    # A new role or store (or turning the account off) logs the person out of every PC: their open
    # session must not keep the old rights. A new full name doesn't.
    if (user.role, user.store_id, user.is_active) != (UserRole(old["role"]), old["store_id"], old["is_active"]):
        _end_sessions(user)

    with transaction():
        audit_service.log(actor, "user.update", "user", user.id, old, _snap(user))
    return user


def reset_pin(user_id: int, data: PinReset, actor: User) -> User:
    user = _get_or_404(user_id)
    user.pin_hash = hash_pin(data.new_pin)
    user.pin_failures, user.pin_locked_until = 0, None  # a new PIN also lifts a lock from wrong guesses
    user.must_change_pin = True  # the admin knows this PIN: the person picks their own at next login
    _end_sessions(user)  # whoever is logged in with the old PIN is logged out
    with transaction():
        audit_service.log(actor, "user.reset_pin", "user", user.id, None, {"pin_changed": True})
    return user


def change_own_pin(user: User, data: PinChange) -> User:
    """The person changes their own PIN (required after first login or an admin reset). Ends their other
    sessions; the caller hands out new tokens."""
    if not check_user_pin(user, data.current_pin):
        raise UnauthorizedError("Current PIN is wrong.")
    if data.new_pin == data.current_pin:
        raise BadRequestError("Choose a new PIN, different from the current one.")
    if data.new_pin.lower() in WEAK_PINS:
        raise BadRequestError("This PIN is too easy to guess. Choose another.")
    user.pin_hash = hash_pin(data.new_pin)
    user.must_change_pin = False
    _end_sessions(user)
    with transaction():
        audit_service.log(user, "user.change_pin", "user", user.id, None, {"pin_changed": True})
    return user


# Never accepted as someone's own PIN: the installer default and the obvious ones.
WEAK_PINS = {"admin123", "1234", "0000", "1111", "123456", "12345678", "password"}


def get_user(user_id: int) -> User:
    return _get_or_404(user_id)


def list_users(
    page: int, per_page: int, is_active: bool | None = None, store_id: int | None = None,
) -> tuple[list[User], int]:
    return UserRepository().list(page=page, per_page=per_page, is_active=is_active, store_id=store_id)


def _end_sessions(user: User) -> None:
    user.session_version = (user.session_version or 0) + 1


def _check_store(role: UserRole, store_id: int | None, new: bool) -> None:
    """Managers and cashiers work at one store; only admins (head office) may have none.
    A store being newly given to someone must exist and be active."""
    if store_id is None:
        if role is not UserRole.ADMIN:
            raise BadRequestError("Choose the store this manager / cashier works at.")
        return
    store = db.session.get(Store, store_id)
    if store is None or (new and not store.is_active):
        raise BadRequestError("Choose an active store.")


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
