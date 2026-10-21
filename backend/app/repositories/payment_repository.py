"""Payment queries."""
from decimal import Decimal

from app.extensions import db
from app.models.enums import PaymentMethod, SaleStatus
from app.models.payment import Payment
from app.models.sale import Sale
from app.repositories.base_repository import BaseRepository


class PaymentRepository(BaseRepository):
    model = Payment

    def cash_total_for_shift(self, shift_id: int) -> Decimal:
        """Cash kept in the drawer from this shift's paid bills (amount = bill total, change excluded)."""
        q = (
            db.select(db.func.coalesce(db.func.sum(Payment.amount), 0))
            .join(Sale, Sale.id == Payment.sale_id)
            .where(Sale.shift_id == shift_id, Sale.status == SaleStatus.PAID, Payment.method == PaymentMethod.CASH)
        )
        return Decimal(db.session.scalar(q))

    def totals_by_method_for_shift(self, shift_id: int) -> dict[PaymentMethod, Decimal]:
        """{method: amount} taken on this shift's paid bills (cash, card, UPI; change excluded)."""
        q = (
            db.select(Payment.method, db.func.sum(Payment.amount))
            .join(Sale, Sale.id == Payment.sale_id)
            .where(Sale.shift_id == shift_id, Sale.status == SaleStatus.PAID)
            .group_by(Payment.method)
        )
        return {method: Decimal(total) for method, total in db.session.execute(q).all()}

    def list_for_sale(self, sale_id: int) -> list[Payment]:
        q = db.select(Payment).where(Payment.sale_id == sale_id).order_by(Payment.id)
        return list(db.session.scalars(q).all())
