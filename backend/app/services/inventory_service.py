"""deduct_for_sale(), add_stock(), adjust(), record_damage(). Every change writes a ledger row."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.errors.exceptions import InsufficientStockError, NotFoundError
from app.models.enums import InventoryTxnType
from app.models.inventory import Inventory, InventoryTransaction
from app.models.sale import SaleItem
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.inventory_schemas import (
    AdjustStockRequest,
    ExpiringBatchOut,
    StockInRequest,
    StockLevelOut,
    StorePriceRequest
    ThresholdRequest,
)
from app.services import audit_service, settings_service
from app.utils.transactions import transaction


def stock_levels(store_id: int) -> list[StockLevelOut]:
    _get_store_or_404(store_id)
    default_threshold = settings_service.get_settings().low_stock_threshold
    out = []
    for product, inv in InventoryRepository().stock_levels(store_id):
        qty = inv.qty_on_hand if inv else Decimal("0")
        own = inv.low_stock_threshold if inv else None
        threshold = own if own is not None else default_threshold
        primary = next((b for b in product.barcodes if b.is_primary), None) or next(iter(product.barcodes), None)
        out.append(StockLevelOut(
            product_id=product.id,
            product_name=product.name,
            barcode=primary.barcode if primary else None,
            qty_on_hand=qty,
            uom=product.uom,
            low_stock_threshold=own,
            effective_threshold=threshold,
            is_low=qty <= threshold,
            base_price=product.price,
            store_price=inv.price if inv else None,
            price=inv.price if inv and inv.price is not None else product.price,
        ))
    return out


def selling_price(store_id: int, product: Product) -> Decimal:
    """What this store charges for the product (before GST): its own price, else the head-office price."""
    row = InventoryRepository().get_for_store_product(store_id, product.id)
    return row.price if row is not None and row.price is not None else product.price


def store_prices(store_id: int, product_ids: list[int]) -> dict[int, Decimal]:
    """{product_id: store price} for products this store has its own price for (one query)."""
    return InventoryRepository().price_overrides(store_id, product_ids)


def set_store_price(data: StorePriceRequest, actor: User) -> Inventory:
    """Set (or clear, with None) this store's own selling price for a product."""
    _check_store_product(data.store_id, data.product_id)
    with transaction():
        row = InventoryRepository().lock_or_create(data.store_id, data.product_id)
        old = row.price
        row.price = data.price
        audit_service.log(
            actor, "inventory.store_price", "inventory", row.id,
            {"price": None if old is None else str(old)},
            {"price": None if data.price is None else str(data.price), "store_id": data.store_id},
        )
    return row



def set_threshold(data: ThresholdRequest, actor: User) -> Inventory:
    """Per-product low-stock level; None falls back to the store-wide default in Settings."""
    _check_store_product(data.store_id, data.product_id)
    with transaction():
        row = InventoryRepository().lock_or_create(data.store_id, data.product_id)
        old = row.low_stock_threshold
        row.low_stock_threshold = data.threshold
        audit_service.log(
            actor, "inventory.threshold", "inventory", row.id,
            {"low_stock_threshold": None if old is None else str(old)},
            {"low_stock_threshold": None if data.threshold is None else str(data.threshold)},
        )
    return row


def stock_in(data: StockInRequest, actor: User) -> Inventory:
    """Goods received: adds to stock and writes a PURCHASE ledger row."""
    _check_store_product(data.store_id, data.product_id)
    repo = InventoryRepository()
    with transaction():
        row = repo.lock_or_create(data.store_id, data.product_id)
        old = row.qty_on_hand
        row.qty_on_hand = old + data.qty
        repo.add_transaction(
            data.store_id, data.product_id, InventoryTxnType.PURCHASE, data.qty,
            notes=data.notes, expiry_date=data.expiry_date,
        )
        audit_service.log(
            actor, "inventory.stock_in", "inventory", row.id,
            {"qty_on_hand": str(old)},
            {"qty_on_hand": str(row.qty_on_hand), "added": str(data.qty)},
        )
    return row


def adjust(data: AdjustStockRequest, actor: User) -> Inventory:
    """Stock-take correction: sets the counted qty and writes an ADJUSTMENT row for the difference."""
    _check_store_product(data.store_id, data.product_id)
    repo = InventoryRepository()
    with transaction():
        row = repo.lock_or_create(data.store_id, data.product_id)
        old = row.qty_on_hand
        delta = data.new_qty - old
        row.qty_on_hand = data.new_qty
        if delta != 0:
            repo.add_transaction(
                data.store_id, data.product_id, InventoryTxnType.ADJUSTMENT, delta, notes=data.notes
            )
        audit_service.log(
            actor, "inventory.adjust", "inventory", row.id,
            {"qty_on_hand": str(old)}, {"qty_on_hand": str(data.new_qty), "reason": data.notes},
        )
    return row


def expiring_soon(store_id: int, days: int = 30) -> list[ExpiringBatchOut]:
    """Products that have at least one purchase batch expiring within `days` days and qty > 0."""
    _get_store_or_404(store_id)
    today = date.today()
    out = []
    for product, inv, nearest_expiry in InventoryRepository().expiring_batches(store_id, days):
        primary = next((b for b in product.barcodes if b.is_primary), None) or next(iter(product.barcodes), None)
        out.append(ExpiringBatchOut(
            product_id=product.id,
            product_name=product.name,
            barcode=primary.barcode if primary else None,
            qty_on_hand=inv.qty_on_hand,
            uom=product.uom,
            nearest_expiry=nearest_expiry,
            days_to_expiry=(nearest_expiry - today).days,
        ))
    return out


def ledger(store_id: int, product_id: int | None = None) -> list[InventoryTransaction]:
    _get_store_or_404(store_id)
    return InventoryRepository().list_transactions(store_id, product_id)


def _get_store_or_404(store_id: int) -> None:
    if StoreRepository().get_by_id(store_id) is None:
        raise NotFoundError(f"Store {store_id} not found.")


def _check_store_product(store_id: int, product_id: int) -> None:
    _get_store_or_404(store_id)
    product = ProductRepository().get_by_id(product_id)
    if product is None or product.store_id not in (None, store_id):
        raise NotFoundError(f"Product {product_id} not found in store {store_id}.")


def deduct_for_sale(store_id: int, items: list[SaleItem], sale_id: int) -> None:
    """Locks the stock rows (SELECT ... FOR UPDATE), decrements them and writes SALE ledger rows.

    Must run inside the caller's transaction. Raises InsufficientStockError listing
    every short line, so nothing is deducted unless the whole bill can be fulfilled.
    """
    wanted: dict[int, int] = {}
    names: dict[int, str] = {}
    for item in items:
        wanted[item.product_id] = wanted.get(item.product_id, 0) + item.qty
        names[item.product_id] = item.product_name

    repo = InventoryRepository()
    rows = {row.product_id: row for row in repo.lock_rows(store_id, sorted(wanted))}

    shortages = []
    for product_id, qty in wanted.items():
        available = rows[product_id].qty_on_hand if product_id in rows else 0
        if available < qty:
            shortages.append({
                "product_id": product_id,
                "product_name": names[product_id],
                "requested": qty,
                "available": float(available),
            })
    if shortages:
        lines = ", ".join(
            f"{s['product_name']} (need {_qty_text(s['requested'])}, only {_qty_text(s['available'])} in stock)"
            for s in shortages
        )
        raise InsufficientStockError(f"Not enough stock: {lines}.", details=shortages)

    for product_id, qty in wanted.items():
        rows[product_id].qty_on_hand -= qty
        # Ledger qty is signed: negative = stock out.
        repo.add_transaction(store_id, product_id, InventoryTxnType.SALE, -qty, reference_id=sale_id)


def _qty_text(qty) -> str:
    """3.000 -> "3", 1.250 -> "1.25" (weighed items)."""
    d = Decimal(str(qty)).normalize()
    return f"{d:f}"
