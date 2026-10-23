"""deduct_for_sale(), stock_in(), adjust(), write_off_batch(). Every change writes a ledger row and goes through
batch_service, so the batches always add up to the stock."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.errors.exceptions import AppError, InsufficientStockError, NotFoundError
from app.extensions import db
from app.models.enums import InventoryTxnType
from app.models.inventory import Inventory, InventoryTransaction, StockBatch
from app.models.product import Product
from app.models.sale import SaleItem
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.inventory_schemas import (
    AdjustStockRequest,
    BatchOut,
    BatchWriteOffRequest,
    ExpiringBatchOut,
    StockInRequest,
    StockLevelOut,
    ThresholdRequest,
    StorePriceRequest,
)
from app.services import audit_service, batch_service, settings_service
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


def cost_price(store_id: int, product: Product) -> Decimal | None:
    """Purchase cost per unit (before GST): this store's weighted average, else the product's default cost."""
    row = InventoryRepository().get_for_store_product(store_id, product.id)
    return row.avg_cost if row is not None and row.avg_cost is not None else product.cost_price


COST_PLACES = Decimal("0.0001")


def add_purchase_cost(row: Inventory, product: Product, qty: Decimal, unit_cost: Decimal) -> None:
    """Weighted-average cost after `qty` units arrive at `unit_cost`. Call before qty_on_hand goes up."""
    on_hand = Decimal(str(row.qty_on_hand))
    old = row.avg_cost if row.avg_cost is not None else product.cost_price
    if on_hand <= 0 or old is None:
        row.avg_cost = unit_cost.quantize(COST_PLACES)
    else:
        row.avg_cost = ((on_hand * old + qty * unit_cost) / (on_hand + qty)).quantize(COST_PLACES)


def store_avg_costs(store_id: int, product_ids: list[int]) -> dict[int, Decimal]:
    """{product_id: weighted-average cost} for this store (one query)."""
    return InventoryRepository().avg_costs(store_id, product_ids)


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
        batch_service.add(
            data.store_id, data.product_id, data.qty, source="stock_in",
            batch_number=data.batch_number, expiry_date=data.expiry_date,
        )
        repo.add_transaction(
            data.store_id, data.product_id, InventoryTxnType.PURCHASE, data.qty,
            notes=data.notes, expiry_date=data.expiry_date,
        )
        audit_service.log(
            actor, "inventory.stock_in", "inventory", row.id,
            {"qty_on_hand": str(old)},
            {"qty_on_hand": str(row.qty_on_hand), "added": str(data.qty),
             **({"batch": data.batch_number} if data.batch_number else {})},
        )
    return row


def expiring_soon(store_id: int, days: int = 30) -> list[ExpiringBatchOut]:
    """Batches with stock that expire within `days` days or have already expired, soonest first."""
    _get_store_or_404(store_id)
    today = date.today()
    out = []
    for batch, product, inv in batch_service.expiring(store_id, days):
        out.append(ExpiringBatchOut(
            product_id=product.id,
            product_name=product.name,
            barcode=product.barcodes[0].barcode if product.barcodes else None,
            qty_on_hand=inv.qty_on_hand,
            uom=product.uom,
            nearest_expiry=batch.expiry_date,
            days_to_expiry=(batch.expiry_date - today).days,
            batch_id=batch.id,
            batch_number=batch.batch_number,
            batch_qty=batch.qty_remaining,
        ))
    return out


def list_batches(store_id: int, product_id: int) -> list[BatchOut]:
    """A product's batches with stock, in the order sales will take them."""
    _check_store_product(store_id, product_id)
    today = date.today()
    return [
        BatchOut(
            id=b.id, batch_number=b.batch_number, mfg_date=b.mfg_date, expiry_date=b.expiry_date,
            qty_received=b.qty_received, qty_remaining=b.qty_remaining, source=b.source, received_at=b.received_at,
            days_to_expiry=(b.expiry_date - today).days if b.expiry_date else None,
        )
        for b in batch_service.in_stock(store_id, product_id)
    ]


def write_off_batch(batch_id: int, data: BatchWriteOffRequest, actor: User, store_ids: set[int] | None) -> StockBatch:
    """Takes expired / damaged goods of one batch out of stock. store_ids: the stores the actor may change
    (None = all)."""
    batch = db.session.get(StockBatch, batch_id)
    if batch is None or (store_ids is not None and batch.store_id not in store_ids):
        raise NotFoundError(f"Batch {batch_id} not found.")
    repo = InventoryRepository()
    with transaction():
        row = repo.lock_or_create(batch.store_id, batch.product_id)
        db.session.refresh(batch, with_for_update=True)
        qty = data.qty if data.qty is not None else Decimal(str(batch.qty_remaining))
        if qty <= 0 or qty > batch.qty_remaining:
            raise AppError(f"This batch has {_qty_text(batch.qty_remaining)} left; write off at most that.")
        if qty > row.qty_on_hand:
            raise AppError(f"Only {_qty_text(row.qty_on_hand)} in stock.")
        batch.qty_remaining = Decimal(str(batch.qty_remaining)) - qty
        row.qty_on_hand = Decimal(str(row.qty_on_hand)) - qty
        label = batch.batch_number or f"#{batch.id}"
        repo.add_transaction(
            batch.store_id, batch.product_id, InventoryTxnType.ADJUSTMENT, -qty,
            notes=f"Write-off batch {label}: {data.reason}", expiry_date=batch.expiry_date,
        )
        audit_service.log(
            actor, "inventory.write_off", "stock_batch", batch.id,
            {"qty_remaining": str(batch.qty_remaining + qty)},
            {"qty_remaining": str(batch.qty_remaining), "written_off": str(qty), "reason": data.reason},
        )
    return batch


def adjust(data: AdjustStockRequest, actor: User) -> Inventory:
    """Stock-take correction: sets the counted qty and writes an ADJUSTMENT row for the difference."""
    _check_store_product(data.store_id, data.product_id)
    repo = InventoryRepository()
    with transaction():
        row = repo.lock_or_create(data.store_id, data.product_id)
        old = row.qty_on_hand
        delta = data.new_qty - old
        row.qty_on_hand = data.new_qty
        if delta > 0:  # found more than recorded: a batch of its own (no expiry known)
            batch_service.add(data.store_id, data.product_id, delta, source="adjustment")
        elif delta < 0:  # less on the shelf: gone from the batches that would have been sold first
            batch_service.take(data.store_id, data.product_id, -delta)
        if delta != 0:
            repo.add_transaction(
                data.store_id, data.product_id, InventoryTxnType.ADJUSTMENT, delta, notes=data.notes
            )
        audit_service.log(
            actor, "inventory.adjust", "inventory", row.id,
            {"qty_on_hand": str(old)}, {"qty_on_hand": str(data.new_qty), "reason": data.notes},
        )
    return row


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
    for item in sorted(items, key=lambda i: (i.product_id, i.id)):  # earliest-expiring batches first (FEFO)
        batch_service.take_for_sale_item(store_id, item)


def deduct_for_offline_sale(store_id: int, items: list[SaleItem], sale_id: int) -> list[dict]:
    """deduct_for_sale() for a bill made while the server was unreachable. The goods have already left the shop,
    so it never refuses: stock goes down to at most 0 and what the records didn't have is returned (and noted on
    the ledger row) for the manager to check. Must run inside the caller's transaction."""
    wanted: dict[int, Decimal] = {}
    names: dict[int, str] = {}
    for item in items:
        wanted[item.product_id] = wanted.get(item.product_id, Decimal("0")) + Decimal(str(item.qty))
        names[item.product_id] = item.product_name

    repo = InventoryRepository()
    shortages = []
    for product_id in sorted(wanted):  # same lock order as sales: no deadlocks
        qty = wanted[product_id]
        row = repo.lock_or_create(store_id, product_id)
        available = Decimal(str(row.qty_on_hand))
        taken = min(qty, available)
        row.qty_on_hand = available - taken
        note = None
        if taken < qty:
            shortages.append({"product_id": product_id, "product_name": names[product_id],
                              "sold": str(qty), "in_stock": str(available)})
            note = f"Offline bill: sold {_qty_text(qty)}, records had {_qty_text(available)}"
        repo.add_transaction(store_id, product_id, InventoryTxnType.SALE, -taken, reference_id=sale_id, notes=note)
    for item in sorted(items, key=lambda i: (i.product_id, i.id)):
        batch_service.take_for_sale_item(store_id, item)
    return shortages


def restock_for_return(store_id: int, lines, return_id: int, note: str) -> None:
    """Puts returned items back on the shelf (into the batches the bill took them from) and writes RETURN ledger
    rows (reference_id = the return).

    `lines` need product_id, qty and sale_item_id. Must run inside the caller's transaction.
    """
    repo = InventoryRepository()
    for line in sorted(lines, key=lambda ln: ln.product_id):  # same lock order as sales: no deadlocks
        row = repo.lock_or_create(store_id, line.product_id)
        row.qty_on_hand += line.qty
        batch_service.give_back(store_id, line.product_id, line.qty, getattr(line, "sale_item_id", None), return_id)
        repo.add_transaction(store_id, line.product_id, InventoryTxnType.RETURN, line.qty, reference_id=return_id, notes=note)


def _qty_text(qty) -> str:
    """3.000 -> "3", 1.250 -> "1.25" (weighed items)."""
    d = Decimal(str(qty)).normalize()
    return f"{d:f}"
