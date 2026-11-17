"""Godown (back room) stock vs shop-shelf stock.

How it is stored: Inventory.qty_on_hand stays the WHOLE stock of a product in a store, exactly as before, so
billing, batches, reports and the offline catalogue don't change. Inventory.godown_qty is the part of that stock
kept in the godown. What is on the shop shelf is simply qty_on_hand - godown_qty.

Rules:
- Goods received (GRN) go into the godown when Settings → godown_enabled is on (unless marked "straight to shelf").
- Staff move goods godown → shelf with transfer(); every move is a StockTransfer row.
- A bill takes from the shelf. If the shelf (as recorded) runs short, the bill still goes through and the rest is
  taken from the godown: settle_after_stock_out() records that as an automatic transfer, so the manager can see
  which shelves were refilled without the app being told.
- Returns go back on the shelf.
"""
from __future__ import annotations

from decimal import Decimal

from app.errors.exceptions import AppError
from app.extensions import db
from app.models.inventory import Inventory, StockTransfer
from app.models.product import Product
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.schemas.inventory_schemas import RefillOut, ShelfMinRequest, StockTransferOut, TransferRequest
from app.services import audit_service, settings_service
from app.utils.transactions import transaction

ZERO = Decimal("0")


def is_enabled() -> bool:
    return settings_service.get_settings().godown_enabled


def shop_qty(row: Inventory | None) -> Decimal:
    if row is None:
        return ZERO
    return Decimal(str(row.qty_on_hand)) - Decimal(str(row.godown_qty or 0))


def add_to_godown(row: Inventory, qty: Decimal) -> None:
    """Call right AFTER row.qty_on_hand went up by qty: that new stock is in the godown."""
    row.godown_qty = Decimal(str(row.godown_qty or 0)) + Decimal(str(qty))


def settle_after_stock_out(row: Inventory, reason: str = "auto_sale", reference_id: int | None = None) -> Decimal:
    """Call right AFTER row.qty_on_hand went down (sale, write-off), before anything else touches the database.

    The shelf is used first. If it didn't have enough, the godown figure is now bigger than the whole stock:
    the missing part must have come from the godown, so godown_qty comes down to match and an automatic transfer
    is recorded. Returns the quantity taken from the godown (0 when the shelf had enough)."""
    total = Decimal(str(row.qty_on_hand))
    godown = Decimal(str(row.godown_qty or 0))
    pulled = godown - total
    if pulled <= 0:
        return ZERO
    row.godown_qty = total
    db.session.add(StockTransfer(
        store_id=row.store_id, product_id=row.product_id, qty=pulled, direction="to_shop", reason=reason,
        reference_id=reference_id, notes="Shelf was short: taken from the godown",
    ))
    return pulled


def transfer(data: TransferRequest, actor: User) -> Inventory:
    """Staff moved goods godown → shelf (or back). The whole stock doesn't change."""
    from app.services.inventory_service import _check_store_product, _qty_text

    _check_store_product(data.store_id, data.product_id)
    with transaction():
        row = InventoryRepository().lock_or_create(data.store_id, data.product_id)
        godown = Decimal(str(row.godown_qty))
        shop = shop_qty(row)
        if data.direction == "to_shop":
            if data.qty > godown:
                raise AppError(f"Only {_qty_text(godown)} in the godown.")
            row.godown_qty = godown - data.qty
        else:
            if data.qty > shop:
                raise AppError(f"Only {_qty_text(shop)} on the shop shelf.")
            row.godown_qty = godown + data.qty
        db.session.add(StockTransfer(
            store_id=data.store_id, product_id=data.product_id, qty=data.qty, direction=data.direction,
            reason="manual", user_id=actor.id, notes=data.notes,
        ))
        audit_service.log(
            actor, "inventory.transfer", "inventory", row.id,
            {"godown_qty": str(godown)},
            {"godown_qty": str(row.godown_qty), "moved": str(data.qty), "direction": data.direction},
        )
    return row


def set_shelf_min(data: ShelfMinRequest, actor: User) -> Inventory:
    from app.services.inventory_service import _check_store_product

    _check_store_product(data.store_id, data.product_id)
    with transaction():
        row = InventoryRepository().lock_or_create(data.store_id, data.product_id)
        old = row.shelf_min_qty
        row.shelf_min_qty = data.shelf_min_qty
        audit_service.log(
            actor, "inventory.shelf_min", "inventory", row.id,
            {"shelf_min_qty": None if old is None else str(old)},
            {"shelf_min_qty": None if data.shelf_min_qty is None else str(data.shelf_min_qty)},
        )
    return row


def needs_refill(row: Inventory | None) -> bool:
    if row is None or row.shelf_min_qty is None or not row.godown_qty:
        return False
    return shop_qty(row) <= row.shelf_min_qty


def refill_list(store_id: int) -> list[RefillOut]:
    """Shelves to refill: at or below their shelf level, with stock waiting in the godown. Emptiest shelf first."""
    rows = db.session.execute(
        db.select(Inventory, Product)
        .join(Product, Product.id == Inventory.product_id)
        .where(
            Inventory.store_id == store_id,
            Product.is_active.is_(True),
            Inventory.shelf_min_qty.is_not(None),
            Inventory.godown_qty > 0,
            Inventory.qty_on_hand - Inventory.godown_qty <= Inventory.shelf_min_qty,
        )
        .order_by(Inventory.qty_on_hand - Inventory.godown_qty, Product.name)
    ).all()
    return [
        RefillOut(
            product_id=p.id, product_name=p.name, uom=p.uom, shop_qty=shop_qty(inv),
            godown_qty=inv.godown_qty, shelf_min_qty=inv.shelf_min_qty,
        )
        for inv, p in rows
    ]


def recent_transfers(store_id: int, product_id: int | None = None, limit: int = 100) -> list[StockTransferOut]:
    q = db.select(StockTransfer).where(StockTransfer.store_id == store_id)
    if product_id is not None:
        q = q.where(StockTransfer.product_id == product_id)
    rows = db.session.scalars(q.order_by(StockTransfer.id.desc()).limit(limit)).all()
    return [
        StockTransferOut(
            id=t.id, product_id=t.product_id, product_name=t.product.name, qty=t.qty, direction=t.direction,
            reason=t.reason, reference_id=t.reference_id, notes=t.notes, created_at=t.created_at,
            user_name=(t.user.full_name or t.user.username) if t.user else None,
        )
        for t in rows
    ]
