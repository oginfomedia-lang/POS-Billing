"""Inventory queries; lock_rows() uses SELECT FOR UPDATE for safe stock decrements."""
from sqlalchemy import text

from app.extensions import db
from app.models.inventory import Inventory, InventoryTransaction
from app.models.enums import InventoryTxnType
from app.repositories.base_repository import BaseRepository


class InventoryRepository(BaseRepository):
    model = Inventory

    def get_for_store_product(self, store_id: int, product_id: int) -> Inventory | None:
        return db.session.scalar(
            db.select(Inventory)
            .where(Inventory.store_id == store_id)
            .where(Inventory.product_id == product_id)
        )

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
