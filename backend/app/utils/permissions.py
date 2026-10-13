"""Role -> permission map and require_permission decorator."""
from functools import wraps

from flask_jwt_extended import get_jwt, verify_jwt_in_request

from app.errors.exceptions import PermissionDeniedError

# Billing operations every role can perform.
POS_PERMISSIONS = {
    "sales.create",
    "sales.read",
    "sales.void",
}

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
        "products.create",
        "products.read",
        "products.update",
        "categories.create",
        "categories.read",
        "categories.update",
        "shifts.read",
        "shifts.manage",
        "inventory.read",
        "inventory.manage",
        "discounts.read",
        "discounts.manage",
        "reports.read",
        "settings.read",
        "settings.manage",
        "backup.read",
        "backup.manage",
        "backup.upload",
        "backup.restore",
        "backup.replication",
        "suppliers.read",
        "suppliers.create",
        "suppliers.update",
        "suppliers.delete",
        "purchases.read",
        "purchases.create",
        "purchases.update",
        "purchases.cancel",
        "purchases.receive",
        "purchases.approve",
        "invoices.read",
        "invoices.create",
        "invoices.update",
        "payments.read",
        "payments.create",
        "payments.void",
        "documents.upload",
        "documents.delete",
        *POS_PERMISSIONS,
    },
    "manager": {
        "users.read",
        "stores.read",
        "counters.read",
        "products.create",
        "products.read",
        "products.update",
        "categories.create",
        "categories.read",
        "categories.update",
        "shifts.read",
        "shifts.manage",
        "inventory.read",
        "inventory.manage",
        "discounts.read",
        "discounts.manage",
        "reports.read",
        "settings.read",
        "suppliers.read",
        "suppliers.create",
        "suppliers.update",
        "purchases.read",
        "purchases.create",
        "purchases.update",
        "purchases.cancel",
        "purchases.receive",
        "purchases.approve",
        "invoices.read",
        "invoices.create",
        "invoices.update",
        "payments.read",
        "payments.create",
        "payments.void",
        "documents.upload",
        "documents.delete",
        *POS_PERMISSIONS,
    },
    "cashier": {
        "stores.read",
        "counters.read",
        "products.read",
        "categories.read",
        "shifts.read",
        "shifts.manage",
        "inventory.read",
        *POS_PERMISSIONS,
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
