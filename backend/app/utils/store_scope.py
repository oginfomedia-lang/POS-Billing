"""Which store's data a user may see or change.

All branches share one database; every store-owned row (stock, sales, shifts, counters,
offers, staff) carries a store_id. Admins (head office) can work in any store, or across
all stores. Managers and cashiers are locked to the store on their account — enforced
here on the server, not just hidden in the UI.
"""
from app.errors.exceptions import PermissionDeniedError
from app.models.enums import UserRole
from app.models.user import User


def is_head_office(actor: User) -> bool:
    return actor.role is UserRole.ADMIN


def scoped_store_id(actor: User, requested: int | None) -> int | None:
    """The store a list/report may cover. None means "all stores" (admins only)."""
    if is_head_office(actor):
        return requested
    if actor.store_id is None:
        raise PermissionDeniedError("Your account is not assigned to a store.")
    if requested is not None and requested != actor.store_id:
        raise PermissionDeniedError("You can only access your own store.")
    return actor.store_id


def require_store_access(actor: User, store_id: int | None) -> None:
    """For changes to one store's data. store_id None = an all-stores record (head office only)."""
    if is_head_office(actor):
        return
    if store_id is None or store_id != actor.store_id:
        raise PermissionDeniedError("You can only access your own store.")
