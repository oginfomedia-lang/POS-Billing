"""Inventory queries; lock_rows() uses SELECT FOR UPDATE for safe stock decrements."""
from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.inventory import Inventory, InventoryTransaction
from app.models.enums import InventoryTxnType
from app.models.product import Product
from app.repositories.base_repository import BaseRepository


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

    def stock_levels(self, store_id: int) -> list[tuple[Product, Inventory | None]]:
        """Every active product sold in this store, with its stock row (None = never stocked)."""
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
    ) -> InventoryTransaction:
        txn = InventoryTransaction(
            store_id=store_id,
            product_id=product_id,
            txn_type=txn_type,
            qty=qty,
            reference_id=reference_id,
            notes=notes,
        )
        db.session.add(txn)
        return txn
