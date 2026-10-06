"""Imports every model so Alembic can detect all tables."""
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.inventory import Inventory  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.product import Product, ProductBarcode  # noqa: F401
from app.models.sale import BillSequence, Sale, SaleItem  # noqa: F401
from app.models.shift import CashierShift  # noqa: F401
from app.models.store import Counter, Store  # noqa: F401
from app.models.user import User  # noqa: F401
