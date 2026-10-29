"""Inventory queries; lock_rows() uses SELECT FOR UPDATE for safe stock decrements."""
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.inventory import Inventory, InventoryTransaction
from app.models.enums import InventoryTxnType
from app.models.product import Product
from app.repositories.base_repository import BaseRepository
from app.repositories.product_repository import search_filter


class InventoryRepository(BaseRepository):
    model = Inventory

    def get_for_store_product(self, store_id: int, product_id: int) -> Inventory | None:
        return db.session.scalar(
            db.select(Inventory)
            .where(Inventory.store_id == store_id)
            .where(Inventory.product_id == product_id)
        )

    def price_overrides(self, store_id: int, product_ids: list[int]) -> dict:
        """{product_id: price} for this store's own prices among product_ids."""
        if not product_ids:
            return {}
        q = db.select(Inventory.product_id, Inventory.price).where(
            Inventory.store_id == store_id,
            Inventory.product_id.in_(product_ids),
            Inventory.price.is_not(None),
        )
        return dict(db.session.execute(q).all())

    def avg_costs(self, store_id: int, product_ids: list[int]) -> dict:
        """{product_id: avg_cost} for this store's products that have one."""
        if not product_ids:
            return {}
        q = db.select(Inventory.product_id, Inventory.avg_cost).where(
            Inventory.store_id == store_id,
            Inventory.product_id.in_(product_ids),
            Inventory.avg_cost.is_not(None),
        )
        return dict(db.session.execute(q).all())

    def lock_rows(self, store_id: int, product_ids: list[int]) -> list[Inventory]:
        """Return locked Inventory rows for the given products (SELECT FOR UPDATE)."""
        rows = db.session.scalars(
            db.select(Inventory)
            .where(Inventory.store_id == store_id)
            .where(Inventory.product_id.in_(product_ids))
            .order_by(Inventory.product_id)
            .with_for_update()
        ).all()
        return list(rows)

    def lock_or_create(self, store_id: int, product_id: int) -> Inventory:
        """Returns the stock row locked FOR UPDATE, creating it at 0 first if missing (race-safe)."""
        db.session.execute(
            insert(Inventory)
            .values(store_id=store_id, product_id=product_id, qty_on_hand=0)
            .on_conflict_do_nothing(index_elements=[Inventory.store_id, Inventory.product_id])
        )
        return db.session.scalar(
            db.select(Inventory)
            .where(Inventory.store_id == store_id, Inventory.product_id == product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    def stock_levels(self, store_id: int, search: str | None = None) -> list[tuple[Product, Inventory | None]]:
        """Every active product sold in this store, with its stock row (None = never stocked).
        search: same match as the Products list (name, SKU, barcode, or how the name sounds)."""
        q = (
            db.select(Product, Inventory)
            .outerjoin(
                Inventory,
                (Inventory.product_id == Product.id) & (Inventory.store_id == store_id),
            )
            .where(Product.is_active.is_(True))
            .where((Product.store_id == store_id) | (Product.store_id.is_(None)))
            .order_by(Product.name)
        )
        if search:
            q = q.where(search_filter(search))
        return [(p, inv) for p, inv in db.session.execute(q).all()]

    def list_transactions(
        self, store_id: int, product_id: int | None = None, limit: int = 100
    ) -> list[InventoryTransaction]:
        q = db.select(InventoryTransaction).where(InventoryTransaction.store_id == store_id)
        if product_id is not None:
            q = q.where(InventoryTransaction.product_id == product_id)
        q = q.order_by(InventoryTransaction.id.desc()).limit(limit)
        return list(db.session.scalars(q).all())

    def add_transaction(
        self,
        store_id: int,
        product_id: int,
        txn_type: InventoryTxnType,
        qty: float,
        reference_id: int | None = None,
        notes: str | None = None,
        expiry_date: date | None = None,
    ) -> InventoryTransaction:
        txn = InventoryTransaction(
            store_id=store_id,
            product_id=product_id,
            txn_type=txn_type,
            qty=qty,
            reference_id=reference_id,
            notes=notes,
            expiry_date=expiry_date,
        )
        db.session.add(txn)
        return txn

    def expiring_batches(self, store_id: int, days: int = 30) -> list[tuple]:
        """Products with at least one purchase batch expiring within `days` and qty_on_hand > 0."""
        today = date.today()
        cutoff = today + timedelta(days=days)
        q = (
            db.select(
                Product,
                Inventory,
                func.min(InventoryTransaction.expiry_date).label("nearest_expiry"),
            )
            .join(Inventory, (Inventory.product_id == Product.id) & (Inventory.store_id == store_id))
            .join(
                InventoryTransaction,
                (InventoryTransaction.product_id == Product.id)
                & (InventoryTransaction.store_id == store_id)
                & (InventoryTransaction.txn_type == InventoryTxnType.PURCHASE)
                & (InventoryTransaction.expiry_date.isnot(None))
                & (InventoryTransaction.expiry_date >= today)
                & (InventoryTransaction.expiry_date <= cutoff),
            )
            .where(Inventory.qty_on_hand > 0)
            .group_by(Product.id, Inventory.id)
            .order_by(func.min(InventoryTransaction.expiry_date))
        )
        return list(db.session.execute(q).all())
        """Return one row per product with any purchase batch expiring within `days` days.

        Filters to products that still have qty_on_hand > 0.
        Returns tuples of (Product, Inventory, nearest_expiry_date).
        """
        today = date.today()
        cutoff = today + timedelta(days=days)

        nearest = (
            db.select(
                InventoryTransaction.product_id,
                db.func.min(InventoryTransaction.expiry_date).label("nearest_expiry"),
            )
            .where(
                InventoryTransaction.store_id == store_id,
                InventoryTransaction.txn_type == InventoryTxnType.PURCHASE,
                InventoryTransaction.expiry_date.is_not(None),
                InventoryTransaction.expiry_date >= today,
                InventoryTransaction.expiry_date <= cutoff,
            )
            .group_by(InventoryTransaction.product_id)
            .subquery()
        )

        rows = db.session.execute(
            db.select(Product, Inventory, nearest.c.nearest_expiry)
            .join(nearest, nearest.c.product_id == Product.id)
            .join(
                Inventory,
                (Inventory.product_id == Product.id) & (Inventory.store_id == store_id),
            )
            .where(Product.is_active.is_(True), Inventory.qty_on_hand > 0)
            .order_by(nearest.c.nearest_expiry)
        ).all()
        return rows
