"""Return queries: what was already returned per bill line, cash refunded per shift."""
from decimal import Decimal

from app.extensions import db
from app.models.enums import PaymentMethod
from app.models.returns import SaleReturn, SaleReturnItem
from app.repositories.base_repository import BaseRepository

ZERO = Decimal("0")


class ReturnRepository(BaseRepository):
    model = SaleReturn

    def returned_by_item(self, sale_id: int) -> dict[int, tuple[Decimal, Decimal, Decimal, Decimal]]:
        """{sale_item_id: (qty, line_total, discount_amount, tax_amount)} already returned on this bill."""
        f = db.func
        q = (
            db.select(
                SaleReturnItem.sale_item_id,
                f.sum(SaleReturnItem.qty),
                f.sum(SaleReturnItem.line_total),
                f.sum(SaleReturnItem.discount_amount),
                f.sum(SaleReturnItem.tax_amount),
            )
            .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
            .where(SaleReturn.sale_id == sale_id)
            .group_by(SaleReturnItem.sale_item_id)
        )
        return {row[0]: tuple(Decimal(v) for v in row[1:]) for row in db.session.execute(q).all()}

    def cash_refunds_for_shift(self, shift_id: int) -> Decimal:
        q = db.select(db.func.coalesce(db.func.sum(SaleReturn.refund_amount), 0)).where(
            SaleReturn.shift_id == shift_id, SaleReturn.refund_method == PaymentMethod.CASH
        )
        return Decimal(db.session.scalar(q))

    def list_for_shift(self, shift_id: int) -> list[SaleReturn]:
        """Returns paid out of this shift's drawer, oldest first."""
        q = db.select(SaleReturn).where(SaleReturn.shift_id == shift_id).order_by(SaleReturn.id)
        return list(db.session.scalars(q).all())

    def refunded_by_sale(self, sale_ids: list[int]) -> dict[int, tuple[int, Decimal]]:
        """{sale_id: (number of returns, amount refunded)} on these bills, whichever shift paid them out."""
        if not sale_ids:
            return {}
        q = (
            db.select(SaleReturn.sale_id, db.func.count(SaleReturn.id), db.func.sum(SaleReturn.refund_amount))
            .where(SaleReturn.sale_id.in_(sale_ids))
            .group_by(SaleReturn.sale_id)
        )
        return {sid: (count, Decimal(total)) for sid, count, total in db.session.execute(q).all()}

    def list_for_sale(self, sale_id: int) -> list[SaleReturn]:
        q = db.select(SaleReturn).where(SaleReturn.sale_id == sale_id).order_by(SaleReturn.id)
        return list(db.session.scalars(q).all())
