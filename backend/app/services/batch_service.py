"""Stock batches (lots): add(), take() in FEFO order, give_back() for returns, and the batch lists.

The caller holds the product's Inventory row lock (InventoryRepository.lock_rows / lock_or_create) and changes
Inventory.qty_on_hand by the same amount, in the same transaction, so the batches always add up to it.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case

from app.extensions import db
from app.models.inventory import Inventory, SaleItemBatch, StockBatch
from app.models.product import Product

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


def add(
    store_id: int,
    product_id: int,
    qty: Decimal,
    *,
    source: str,
    batch_number: str | None = None,
    expiry_date: date | None = None,
    mfg_date: date | None = None,
    unit_cost: Decimal | None = None,
    reference_id: int | None = None,
) -> StockBatch:
    batch = StockBatch(
        store_id=store_id,
        product_id=product_id,
        batch_number=(batch_number or "").strip() or None,
        expiry_date=expiry_date,
        mfg_date=mfg_date,
        qty_received=qty,
        qty_remaining=qty,
        unit_cost=unit_cost,
        source=source,
        reference_id=reference_id,
    )
    db.session.add(batch)
    return batch


def fefo_order(today: date | None = None):
    """Unexpired batches first, earliest expiry first; then batches without an expiry; expired ones last, so they
    stay on record for a write-off instead of being "sold" on paper."""
    today = today or date.today()
    expired = case((StockBatch.expiry_date < today, 1), else_=0)
    return (expired, StockBatch.expiry_date.asc().nulls_last(), StockBatch.received_at, StockBatch.id)


def take(store_id: int, product_id: int, qty: Decimal) -> list[tuple[StockBatch, Decimal]]:
    """Takes qty out of the product's batches in FEFO order. Returns [(batch, qty taken from it)]."""
    batches = db.session.scalars(
        db.select(StockBatch)
        .where(StockBatch.store_id == store_id, StockBatch.product_id == product_id, StockBatch.qty_remaining > 0)
        .order_by(*fefo_order())
        .with_for_update()
    ).all()
    left = Decimal(str(qty))
    taken = []
    for batch in batches:
        if left <= 0:
            break
        part = min(Decimal(str(batch.qty_remaining)), left)
        batch.qty_remaining = Decimal(str(batch.qty_remaining)) - part
        taken.append((batch, part))
        left -= part
    if left > 0:
        # Inventory.qty_on_hand allowed it, so the batches are behind (should not happen after the migration).
        # The sale still goes through: the total stock is what counts.
        logger.warning("Batches short by %s for product %s in store %s", left, product_id, store_id)
    return taken


def take_for_sale_item(store_id: int, sale_item) -> None:
    """take() for one bill line, remembering which batches it came from."""
    for batch, part in take(store_id, sale_item.product_id, sale_item.qty):
        db.session.add(SaleItemBatch(sale_item_id=sale_item.id, batch_id=batch.id, qty=part))


def give_back(store_id: int, product_id: int, qty: Decimal, sale_item_id: int | None, return_id: int) -> None:
    """Returned goods go back into the batches the bill took them from. Whatever can't be matched (a bill from
    before batches existed) becomes a new batch without an expiry date."""
    left = Decimal(str(qty))
    if sale_item_id is not None:
        allocations = db.session.scalars(
            db.select(SaleItemBatch)
            .where(SaleItemBatch.sale_item_id == sale_item_id)
            .order_by(SaleItemBatch.id.desc())
            .with_for_update()
        ).all()
        for alloc in allocations:
            if left <= 0:
                break
            room = Decimal(str(alloc.qty)) - Decimal(str(alloc.qty_returned))
            part = min(room, left)
            if part <= 0:
                continue
            alloc.qty_returned = Decimal(str(alloc.qty_returned)) + part
            alloc.batch.qty_remaining = Decimal(str(alloc.batch.qty_remaining)) + part
            left -= part
    if left > 0:
        add(store_id, product_id, left, source="return", reference_id=return_id)


def in_stock(store_id: int, product_id: int) -> list[StockBatch]:
    """The product's batches that still have stock, in the order they will be sold."""
    return list(db.session.scalars(
        db.select(StockBatch)
        .where(StockBatch.store_id == store_id, StockBatch.product_id == product_id, StockBatch.qty_remaining > 0)
        .order_by(*fefo_order())
    ).all())


def expiring(store_id: int, days: int) -> list[tuple[StockBatch, Product, Inventory]]:
    """Batches with stock that expire within `days` days, or have already expired (soonest first)."""
    cutoff = date.today() + timedelta(days=days)
    q = (
        db.select(StockBatch, Product, Inventory)
        .join(Product, Product.id == StockBatch.product_id)
        .join(Inventory, (Inventory.product_id == StockBatch.product_id) & (Inventory.store_id == store_id))
        .where(
            StockBatch.store_id == store_id,
            StockBatch.qty_remaining > 0,
            StockBatch.expiry_date.is_not(None),
            StockBatch.expiry_date <= cutoff,
            Product.is_active.is_(True),
        )
        .order_by(StockBatch.expiry_date, StockBatch.id)
    )
    return [tuple(row) for row in db.session.execute(q).all()]
