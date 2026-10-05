"""Role -> permission map and require_permission decorator."""
from functools import wraps

from flask_jwt_extended import get_jwt, verify_jwt_in_request

from app.errors.exceptions import PermissionDeniedError

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "users.create",
        "users.read",
        "users.update",
        "users.delete",
        "stores.create",
        "stores.read",
        "stores.update",
        "counters.create",
        "counters.read",
        "counters.update",
        "audit.read",
    },
    "manager": {
        "users.read",
        "stores.read",
        "counters.read",
    },
    "cashier": {
        "stores.read",
        "counters.read",
    },
}


def require_permission(permission: str):
    """Decorator: verifies JWT and checks role permission before running the view."""

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            role = claims.get("role", "")
            if permission not in ROLE_PERMISSIONS.get(role, set()):
                raise PermissionDeniedError("You don't have permission for this action.")
            return f(*args, **kwargs)

        return decorated

    return decorator
