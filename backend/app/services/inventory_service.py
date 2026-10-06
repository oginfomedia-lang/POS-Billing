"""deduct_for_sale(), add_stock(), adjust(), record_damage(). Every change writes a ledger row."""
from __future__ import annotations

from app.errors.exceptions import InsufficientStockError
from app.models.sale import SaleItem
from app.repositories.inventory_repository import InventoryRepository


def deduct_for_sale(store_id: int, items: list[SaleItem]) -> None:
    """Locks the stock rows (SELECT ... FOR UPDATE) and decrements them.

    Must run inside the caller's transaction. Raises InsufficientStockError listing
    every short line, so nothing is deducted unless the whole bill can be fulfilled.
    """
    wanted: dict[int, int] = {}
    names: dict[int, str] = {}
    for item in items:
        wanted[item.product_id] = wanted.get(item.product_id, 0) + item.qty
        names[item.product_id] = item.product_name

    rows = InventoryRepository().lock_rows(store_id, sorted(wanted))

    shortages = []
    for product_id, qty in wanted.items():
        available = rows[product_id].qty_on_hand if product_id in rows else 0
        if available < qty:
            shortages.append({
                "product_id": product_id,
                "product_name": names[product_id],
                "requested": qty,
                "available": available,
            })
    if shortages:
        raise InsufficientStockError("Not enough stock for some items.", details=shortages)

    for product_id, qty in wanted.items():
        rows[product_id].qty_on_hand -= qty
