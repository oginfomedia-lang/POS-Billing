"""Inventory queries, lock_rows() with SELECT ... FOR UPDATE ORDER BY product_id, ledger inserts."""
from app.extensions import db
from app.models.inventory import Inventory
from app.repositories.base_repository import BaseRepository


class InventoryRepository(BaseRepository):
    model = Inventory

    def lock_rows(self, store_id: int, product_ids: list[int]) -> dict[int, Inventory]:
        """Locks stock rows in product_id order (consistent order prevents deadlocks)."""
        q = (
            db.select(Inventory)
            .where(Inventory.store_id == store_id, Inventory.product_id.in_(product_ids))
            .order_by(Inventory.product_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return {row.product_id: row for row in db.session.scalars(q).all()}
