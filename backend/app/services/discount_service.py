"""Discount management (audited) and selection of the best offers for a bill.

Rules: each line gets its single best PRODUCT/CATEGORY offer (a category offer also covers its
sub-categories); then the bill gets its single best BILL offer on what's left. So one item offer
and one bill offer can both apply to the same bill.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.errors.exceptions import NotFoundError
from app.extensions import db
from app.models.discount import Discount
from app.models.enums import DiscountScope, DiscountType
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


@dataclass(frozen=True)
class AppliedOffer:
    """The offer chosen for one line, or for the bill. id/name are None when no offer applies."""
    discount_id: int | None
    name: str | None
    amount: Decimal


NO_OFFER = AppliedOffer(None, None, ZERO)


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


def line_discounts(discounts: list[Discount], items: list[SaleItem]) -> list[AppliedOffer]:
    """Best PRODUCT/CATEGORY offer for each item (items must have line_total set)."""
    parents = CategoryRepository().parent_map()
    out = []
    for item in items:
        category_id = item.product.category_id if item.product else None
        family = _with_ancestors(category_id, parents)
        best = NO_OFFER
        for d in discounts:
            matches = (d.scope is DiscountScope.PRODUCT and d.product_id == item.product_id) or (
                d.scope is DiscountScope.CATEGORY and d.category_id in family
            )
            if matches:
                amount = _item_offer_amount(d, item)
                if amount > best.amount:
                    best = AppliedOffer(d.id, d.name, amount)
        out.append(best)
    return out


def best_bill_discount(discounts: list[Discount], amount: Decimal, qualifying_amount: Decimal) -> AppliedOffer:
    """Best BILL offer. The % is taken from `amount` (before GST); the minimum is checked
    against `qualifying_amount` (with GST — the total the customer sees)."""
    best = NO_OFFER
    for d in discounts:
        if d.scope is DiscountScope.BILL and amount > 0 and qualifying_amount >= (d.min_bill_amount or ZERO):
            off = pricing_service.bill_discount(d.discount_type, d.value, amount, d.max_discount_amount)
            if off > best.amount:
                best = AppliedOffer(d.id, d.name, off)
    return best


def _item_offer_amount(d: Discount, item: SaleItem) -> Decimal:
    """Rupees one item offer takes off one line, whatever its type."""
    if d.discount_type is DiscountType.BUY_X_GET_Y:
        return pricing_service.buy_x_get_y_discount(item.unit_price, item.qty, d.buy_qty, d.get_qty, item.line_total)
    if d.discount_type is DiscountType.QTY_PRICE:
        return pricing_service.qty_price_discount(
            item.unit_price, item.qty, item.tax_rate, d.buy_qty, d.value, item.line_total
        )
    return pricing_service.item_discount(d.discount_type, d.value, item.line_total, item.qty, d.max_discount_amount)


def _with_ancestors(category_id: int | None, parents: dict[int, int | None]) -> set[int]:
    """The category plus every parent above it (Chips -> Snacks -> Food).
    Stops if it meets a category twice, so a bad parent loop can't run forever."""
    family: set[int] = set()
    while category_id is not None and category_id not in family:
        family.add(category_id)
        category_id = parents.get(category_id)
    return family
