"""Sale queries: get_for_update(), find_item(), list_held()."""
from app.extensions import db
from app.models.enums import SaleStatus
from app.models.sale import Sale, SaleItem
from app.repositories.base_repository import BaseRepository


class SaleRepository(BaseRepository):
    model = Sale

    def create_draft(self, shift_id: int, store_id: int, counter_id: int | None, cashier_id: int) -> Sale:
        sale = Sale(
            shift_id=shift_id,
            store_id=store_id,
            counter_id=counter_id,
            cashier_id=cashier_id,
            status=SaleStatus.OPEN,
        )
        return self.add(sale)

    def get_for_update(self, sale_id: int) -> Sale | None:
        """Locks the sale row so two requests can't complete/modify it at once."""
        return db.session.scalar(
            db.select(Sale).where(Sale.id == sale_id).with_for_update().execution_options(populate_existing=True)
        )

    def get_by_bill_number(self, bill_number: str, for_update: bool = False) -> Sale | None:
        q = db.select(Sale).where(Sale.bill_number == bill_number)
        if for_update:
            q = q.with_for_update().execution_options(populate_existing=True)
        return db.session.scalar(q)

    def paid_by_mobile(self, mobile: str, store_id: int | None, limit: int = 20) -> list[Sale]:
        """A customer's paid bills, newest first. store_id None = all stores."""
        q = db.select(Sale).where(Sale.customer_mobile == mobile, Sale.status == SaleStatus.PAID)
        if store_id is not None:
            q = q.where(Sale.store_id == store_id)
        return list(db.session.scalars(q.order_by(Sale.completed_at.desc()).limit(limit)).all())

    def list_for_shift(self, shift_id: int) -> list[Sale]:
        """Every bill started on this shift (paid, held, voided, open), oldest first."""
        q = db.select(Sale).where(Sale.shift_id == shift_id).order_by(Sale.completed_at.asc().nulls_last(), Sale.id)
        return list(db.session.scalars(q).all())

    def find_item(self, sale_id: int, product_id: int) -> SaleItem | None:
        return db.session.scalar(
            db.select(SaleItem).where(SaleItem.sale_id == sale_id, SaleItem.product_id == product_id)
        )

    def get_item(self, item_id: int) -> SaleItem | None:
        return db.session.get(SaleItem, item_id)

    def list_open(self, shift_id: int, cashier_id: int) -> list[Sale]:
        q = db.select(Sale).where(
            Sale.shift_id == shift_id,
            Sale.cashier_id == cashier_id,
            Sale.status == SaleStatus.OPEN,
        )
        return list(db.session.scalars(q.order_by(Sale.id.desc())).all())

    def list_held(self, shift_id: int) -> list[Sale]:
        q = db.select(Sale).where(Sale.shift_id == shift_id, Sale.status == SaleStatus.HELD)
        return list(db.session.scalars(q.order_by(Sale.updated_at.desc())).all())
