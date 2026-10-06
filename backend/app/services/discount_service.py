"""Discount management (audited) and selection of the best discount for a bill.

Rules: each line gets the single best PRODUCT/CATEGORY discount; the bill then gets the
single best BILL discount (on the amount after line discounts). Discounts don't stack.
"""
from __future__ import annotations

from decimal import Decimal

from app.errors.exceptions import NotFoundError
from app.extensions import db
from app.models.discount import Discount
from app.models.enums import DiscountScope
from app.models.sale import SaleItem
from app.models.user import User
from app.repositories.category_repository import CategoryRepository
from app.repositories.discount_repository import DiscountRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.discount_schemas import DiscountIn, DiscountOut
from app.services import audit_service, pricing_service
from app.utils.dates import now_ist
from app.utils.transactions import transaction

ZERO = Decimal("0.00")


# ── Admin CRUD ───────────────────────────────────────────────────────────────

def list_discounts() -> list[Discount]:
    return DiscountRepository().list_all()


def create_discount(data: DiscountIn, actor: User) -> Discount:
    _check_refs(data)
    discount = Discount(**data.model_dump())
    with transaction():
        DiscountRepository().add(discount)
        db.session.flush()
        audit_service.log(actor, "discount.create", "discount", discount.id, None, _snap(discount))
    return discount


def update_discount(discount_id: int, data: DiscountIn, actor: User) -> Discount:
    discount = DiscountRepository().get_by_id(discount_id)
    if discount is None:
        raise NotFoundError(f"Discount {discount_id} not found.")
    _check_refs(data)
    old = _snap(discount)
    for field, value in data.model_dump().items():
        setattr(discount, field, value)
    with transaction():
        audit_service.log(actor, "discount.update", "discount", discount.id, old, _snap(discount))
    return discount


def _check_refs(data: DiscountIn) -> None:
    if data.product_id is not None and ProductRepository().get_by_id(data.product_id) is None:
        raise NotFoundError(f"Product {data.product_id} not found.")
    if data.category_id is not None and CategoryRepository().get_by_id(data.category_id) is None:
        raise NotFoundError(f"Category {data.category_id} not found.")
    if data.store_id is not None and StoreRepository().get_by_id(data.store_id) is None:
        raise NotFoundError(f"Store {data.store_id} not found.")


def _snap(d: Discount) -> dict:
    return DiscountOut.model_validate(d).model_dump(mode="json")


# ── Applying discounts while billing ─────────────────────────────────────────

def active_for_store(store_id: int) -> list[Discount]:
    return DiscountRepository().active_for_store(store_id, now_ist())


def line_discounts(discounts: list[Discount], items: list[SaleItem]) -> list[Decimal]:
    """Best PRODUCT/CATEGORY discount for each item (items must have line_total set)."""
    out = []
    for item in items:
        category_id = item.product.category_id if item.product else None
        best = ZERO
        for d in discounts:
            matches = (d.scope is DiscountScope.PRODUCT and d.product_id == item.product_id) or (
                d.scope is DiscountScope.CATEGORY and category_id is not None and d.category_id == category_id
            )
            if matches:
                best = max(best, pricing_service.item_discount(d.discount_type, d.value, item.line_total, item.qty))
        out.append(best)
    return out


def best_bill_discount(discounts: list[Discount], amount: Decimal) -> Decimal:
    best = ZERO
    for d in discounts:
        if d.scope is DiscountScope.BILL and amount > 0 and amount >= (d.min_bill_amount or ZERO):
            best = max(best, pricing_service.bill_discount(d.discount_type, d.value, amount))
    return best
