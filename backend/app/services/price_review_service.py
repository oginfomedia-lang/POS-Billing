"""Review selling prices: products whose price no longer gives the profit wanted, with a suggested price.

The formula (no AI, no rounding to a "nice" number):
    target % = the product's category's target, else its parent category's, ..., else Settings default
    suggested price before GST = cost × (1 + target / 100), rounded UP to the paisa (never below the target)
    price with GST             = price before GST + GST on it (the same maths as a bill line)
    never above MRP: if the price with GST would be more than the MRP, the price is the most the MRP allows
    (rounded DOWN to the paisa), and the row says "capped at MRP" (the target can't be reached).

Cost = products.cost_price: the latest rate paid (before GST, after discount); GST paid to the supplier is claimed
back as input credit, so it is not part of the cost. Profit % is profit on cost: (price − cost) / cost × 100.

A product is listed when it has a cost and its price (before GST) is below cost × (1 + target %), unless someone
already applied or kept a price at this same cost (price_reviewed_cost). A new cost brings it back.
One price for all branches: only the main price (products.price) is checked and changed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal

from sqlalchemy import or_, select

from app.errors.exceptions import BadRequestError, NotFoundError
from app.extensions import db
from app.models.category import Category
from app.models.product import Product
from app.models.user import User
from app.schemas.price_review_schemas import PriceReviewOut, PriceReviewRow
from app.services import audit_service, pricing_service, settings_service
from app.utils.money import round_money
from app.utils.store_scope import is_head_office, require_store_access
from app.utils.transactions import transaction

ZERO = Decimal("0")
PAISA = Decimal("0.01")
HUNDRED = Decimal("100")


@dataclass(frozen=True)
class Suggestion:
    price: Decimal  # before GST
    price_incl: Decimal  # with GST, what the customer pays for one unit
    margin_percent: Decimal | None  # profit on cost; None when the cost is 0
    capped: bool  # the MRP stopped the price below the target


def price_with_gst(price: Decimal, tax_rate: Decimal) -> Decimal:
    """What one unit costs the customer: the same sum as a bill line of qty 1."""
    line_total, tax = pricing_service.line_amounts(price, 1, tax_rate)
    return line_total + tax


def margin_percent(price: Decimal, cost: Decimal) -> Decimal | None:
    if cost <= 0:
        return None
    return round_money((Decimal(price) - cost) / cost * HUNDRED)


def suggest(cost: Decimal, tax_rate: Decimal, mrp: Decimal | None, target: Decimal) -> Suggestion:
    cost, tax_rate, target = Decimal(cost), Decimal(tax_rate), Decimal(target)
    price = (cost * (1 + target / HUNDRED)).quantize(PAISA, rounding=ROUND_UP)
    capped = False
    if mrp is not None and price_with_gst(price, tax_rate) > mrp:
        # The most the MRP allows. GST is rounded to the paisa, so the plain division can be a paisa off either way.
        price = (Decimal(mrp) / (1 + tax_rate / HUNDRED)).quantize(PAISA, rounding=ROUND_DOWN)
        while price > 0 and price_with_gst(price, tax_rate) > mrp:
            price -= PAISA
        while price_with_gst(price + PAISA, tax_rate) <= mrp:
            price += PAISA
        capped = True
    return Suggestion(price, price_with_gst(price, tax_rate), margin_percent(price, cost), capped)


def target_percents() -> tuple[dict[int, Decimal], Decimal]:
    """({category_id: target %}, default): each category's own target, else its parent's, ..., else default."""
    default = settings_service.get_settings().default_margin_percent
    cats = {c.id: c for c in db.session.scalars(select(Category)).all()}
    out: dict[int, Decimal] = {}
    for cid in cats:
        seen: set[int] = set()
        c = cats.get(cid)
        while c is not None and c.id not in seen and c.target_margin_percent is None:
            seen.add(c.id)
            c = cats.get(c.parent_id) if c.parent_id is not None else None
        out[cid] = c.target_margin_percent if c is not None and c.target_margin_percent is not None else default
    return out, default


def _above_mrp(p: Product) -> bool:
    return p.mrp is not None and price_with_gst(Decimal(p.price), p.tax_rate) > p.mrp


def _needs_review(p: Product, target: Decimal) -> bool:
    if p.cost_price is None:
        return False  # nothing to work the price out from (a new product shows once its goods are received)
    if p.details_pending:
        return True  # no selling price yet: always ask
    if _above_mrp(p):
        return True  # selling above MRP is not allowed, whatever was kept before
    if p.price_reviewed_cost is not None and Decimal(p.price_reviewed_cost) == Decimal(p.cost_price):
        return False  # already applied or kept at this cost
    wanted = (Decimal(p.cost_price) * (1 + target / HUNDRED)).quantize(PAISA, rounding=ROUND_DOWN)
    return Decimal(p.price) < wanted


def _row(p: Product, target: Decimal) -> PriceReviewRow:
    cost = Decimal(p.cost_price)
    s = suggest(cost, p.tax_rate, p.mrp, target)
    price = Decimal(p.price)
    return PriceReviewRow(
        product_id=p.id, name=p.name, sku=p.sku, category_name=p.category.name if p.category else None,
        uom=p.uom.value if p.uom else None, cost_price=cost, tax_rate=p.tax_rate, mrp=p.mrp,
        price=price, price_incl=price_with_gst(price, p.tax_rate), margin_percent=margin_percent(price, cost),
        below_cost=price < cost, target_percent=target,
        suggested_price=s.price, suggested_price_incl=s.price_incl, suggested_margin_percent=s.margin_percent,
        capped_at_mrp=s.capped, details_pending=p.details_pending, above_mrp=_above_mrp(p),
    )


def _visible(actor: User):
    """Shared products, and the actor's own store's (head office: all)."""
    if is_head_office(actor):
        return None
    return or_(Product.store_id.is_(None), Product.store_id == actor.store_id)


def review_list(actor: User, product_ids: list[int] | None = None) -> PriceReviewOut:
    """Products to review, the biggest shortfall first (selling below cost, then the lowest profit %).
    product_ids: only these (e.g. the products of one goods receipt)."""
    targets, default = target_percents()
    q = select(Product).where(Product.is_active.is_(True), Product.cost_price.is_not(None))
    scope = _visible(actor)
    if scope is not None:
        q = q.where(scope)
    if product_ids:
        q = q.where(Product.id.in_(product_ids))
    rows = []
    for p in db.session.scalars(q).all():
        target = targets.get(p.category_id, default) if p.category_id else default
        if _needs_review(p, target):
            rows.append(_row(p, target))
    # New products without a price first, then prices above MRP, then selling at a loss, then the lowest profit.
    rows.sort(key=lambda r: (not r.details_pending, not r.above_mrp, not r.below_cost,
                             r.margin_percent if r.margin_percent is not None else ZERO, r.name))
    return PriceReviewOut(items=rows, default_margin_percent=default)


def _get(product_id: int, actor: User) -> Product:
    p = db.session.get(Product, product_id, with_for_update=True)
    if p is None:
        raise NotFoundError(f"Product {product_id} not found.")
    if p.store_id is not None:
        require_store_access(actor, p.store_id)
    if p.cost_price is None:
        raise BadRequestError(f"'{p.name}' has no cost price yet, so its price can't be reviewed.")
    return p


def apply_price(product_id: int, price: Decimal, actor: User) -> PriceReviewRow:
    """Sets the selling price (before GST): the suggested one, or one the user typed. Never above MRP."""
    with transaction():
        p = _get(product_id, actor)
        price = round_money(price)
        if p.mrp is not None and price_with_gst(price, p.tax_rate) > p.mrp:
            raise BadRequestError(
                f"₹{price_with_gst(price, p.tax_rate)} with GST is more than the MRP ₹{p.mrp}. "
                f"A product can't be sold above its MRP."
            )
        old = Decimal(p.price)
        p.price = price
        p.price_reviewed_cost = p.cost_price
        if price > 0:
            p.details_pending = False  # it has a selling price: billing can sell it now
        audit_service.log(
            actor, "product.price_review", "product", p.id,
            {"price": str(old)},
            {"price": str(price), "cost_price": str(p.cost_price), "action": "apply"},
        )
    targets, default = target_percents()
    return _row(p, targets.get(p.category_id, default) if p.category_id else default)


def keep_price(product_id: int, actor: User) -> None:
    """Keep the current price at this cost (e.g. a price set on purpose). Asked again when the cost changes."""
    with transaction():
        p = _get(product_id, actor)
        if p.details_pending:
            raise BadRequestError(f"'{p.name}' has no selling price yet. Type a price and press Apply.")
        if _above_mrp(p):
            raise BadRequestError(f"'{p.name}' sells above its MRP ₹{p.mrp}. Apply a lower price.")
        p.price_reviewed_cost = p.cost_price
        audit_service.log(
            actor, "product.price_review", "product", p.id, None,
            {"price": str(p.price), "cost_price": str(p.cost_price), "action": "keep"},
        )
