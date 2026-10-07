"""Discount management (audited) and selection of the one best offer for a bill.

Rule: only ONE automatic offer applies per bill — whichever saves the customer the most.
Item offers (PRODUCT/CATEGORY; a category offer also covers its sub-categories) and bill
offers all compete. Manager-approved manual discounts are separate and still apply.
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
    """The offer chosen for the bill. id/name are None when no offer applies; amount is the total saved."""
    discount_id: int | None
    name: str | None
    amount: Decimal


NO_OFFER = AppliedOffer(None, None, ZERO)


@dataclass(frozen=True)
class ChosenOffer:
    """The single automatic offer applied to a bill and the rupees it takes off each line."""
    offer: AppliedOffer
    line_amounts: list[Decimal]
    is_bill_offer: bool  # True: a BILL offer spread across lines; False: an item offer


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


def choose_best_offer(
    discounts: list[Discount], items: list[SaleItem], room: list[Decimal], qualifying_amount: Decimal
) -> ChosenOffer:
    """Only ONE automatic offer applies per bill: whichever saves the customer the most in total.

    items must have line_total set. room[i] = what's left of line i after its manual discount
    (an offer can't take a line below zero). A bill offer's % is taken from sum(room) (before GST);
    its minimum is checked against `qualifying_amount` (with GST — the total the customer sees).
    Ties keep the offer found first.
    """
    best = ChosenOffer(NO_OFFER, [ZERO] * len(items), False)
    parents = CategoryRepository().parent_map()
    families = [_with_ancestors(item.product.category_id if item.product else None, parents) for item in items]
    bill_amount = sum(room, ZERO)

    for d in discounts:
        if d.scope is DiscountScope.BILL:
            if bill_amount <= 0 or qualifying_amount < (d.min_bill_amount or ZERO):
                continue
            off = pricing_service.bill_discount(d.discount_type, d.value, bill_amount, d.max_discount_amount)
            if off > best.offer.amount:
                best = ChosenOffer(AppliedOffer(d.id, d.name, off), pricing_service.allocate(off, room), True)
        else:
            lines = [
                min(_item_offer_amount(d, item), r) if _matches(d, item, family) else ZERO
                for item, family, r in zip(items, families, room)
            ]
            total = sum(lines, ZERO)
            if total > best.offer.amount:
                best = ChosenOffer(AppliedOffer(d.id, d.name, total), lines, False)
    return best


def _matches(d: Discount, item: SaleItem, family: set[int]) -> bool:
    """Does this PRODUCT/CATEGORY offer cover the item? `family` = the item's category and its parents."""
    if d.scope is DiscountScope.PRODUCT:
        return d.product_id == item.product_id
    return d.scope is DiscountScope.CATEGORY and d.category_id in family


def _item_offer_amount(d: Discount, item: SaleItem) -> Decimal:
    """Rupees one item offer takes off one line, whatever its type."""
    if d.discount_type is DiscountType.BUY_X_GET_Y:
        return pricing_service.buy_x_get_y_discount(d.buy_qty, d.get_qty, item.line_total)
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
