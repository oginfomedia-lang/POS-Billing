"""Aggregate SQL for reports (sales, GST, shifts, low stock).

All sales figures count PAID bills only, by completed_at in [start, end). store_id=None means all stores.
"""
from datetime import datetime

from app.extensions import db
from app.models.enums import PaymentMethod, SaleStatus, ShiftStatus
from app.models.payment import Payment
from app.models.sale import Sale, SaleItem
from app.models.shift import CashierShift
from app.models.store import Counter
from app.models.user import User

IST_ZONE = "Asia/Kolkata"


class ReportRepository:
    def _paid(self, store_id: int | None, start: datetime, end: datetime) -> list:
        conds = [Sale.status == SaleStatus.PAID, Sale.completed_at >= start, Sale.completed_at < end]
        if store_id is not None:
            conds.append(Sale.store_id == store_id)
        return conds

    def summary(self, store_id: int | None, start: datetime, end: datetime):
        f = db.func
        q = db.select(
            f.count(Sale.id).label("bills"),
            f.coalesce(f.sum(Sale.subtotal), 0).label("subtotal"),
            f.coalesce(f.sum(Sale.discount_amount), 0).label("discount"),
            f.coalesce(f.sum(Sale.tax_amount), 0).label("tax"),
            f.coalesce(f.sum(Sale.total), 0).label("total"),
        ).where(*self._paid(store_id, start, end))
        return db.session.execute(q).one()

    def voided_count(self, store_id: int | None, start: datetime, end: datetime) -> int:
        q = db.select(db.func.count(Sale.id)).where(
            Sale.status == SaleStatus.VOIDED, Sale.updated_at >= start, Sale.updated_at < end
        )
        if store_id is not None:
            q = q.where(Sale.store_id == store_id)
        return db.session.scalar(q) or 0

    def by_payment_method(self, store_id: int | None, start: datetime, end: datetime):
        q = (
            db.select(
                Payment.method,
                db.func.count(db.distinct(Payment.sale_id)).label("bills"),
                db.func.sum(Payment.amount).label("amount"),
            )
            .join(Sale, Sale.id == Payment.sale_id)
            .where(*self._paid(store_id, start, end))
            .group_by(Payment.method)
            .order_by(Payment.method)
        )
        return db.session.execute(q).all()

    def daily(self, store_id: int | None, start: datetime, end: datetime):
        day = db.func.date(db.func.timezone(IST_ZONE, Sale.completed_at)).label("day")
        q = (
            db.select(day, db.func.count(Sale.id).label("bills"), db.func.sum(Sale.total).label("total"))
            .where(*self._paid(store_id, start, end))
            .group_by(day)
            .order_by(day)
        )
        return db.session.execute(q).all()

    def gst_by_rate(self, store_id: int | None, start: datetime, end: datetime):
        q = (
            db.select(
                SaleItem.tax_rate,
                db.func.sum(SaleItem.line_total - SaleItem.discount_amount).label("taxable"),
                db.func.sum(SaleItem.tax_amount).label("tax"),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*self._paid(store_id, start, end))
            .group_by(SaleItem.tax_rate)
            .order_by(SaleItem.tax_rate)
        )
        return db.session.execute(q).all()

    def top_products(self, store_id: int | None, start: datetime, end: datetime, limit: int = 10):
        amount = db.func.sum(SaleItem.line_total - SaleItem.discount_amount).label("amount")
        q = (
            db.select(
                SaleItem.product_id,
                db.func.max(SaleItem.product_name).label("product_name"),
                db.func.sum(SaleItem.qty).label("qty"),
                amount,
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*self._paid(store_id, start, end))
            .group_by(SaleItem.product_id)
            .order_by(amount.desc())
            .limit(limit)
        )
        return db.session.execute(q).all()

    def offer_usage(self, store_id: int | None, start: datetime, end: datetime):
        """(kind, name, bills, amount) for item offers, bill offers and manual discounts on paid bills."""
        paid = self._paid(store_id, start, end)
        item = (
            db.select(
                db.literal("item"),
                db.func.max(SaleItem.offer_name),
                db.func.count(db.distinct(SaleItem.sale_id)),
                db.func.sum(SaleItem.offer_discount),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*paid, SaleItem.offer_id.is_not(None))
            .group_by(SaleItem.offer_id)
        )
        bill = (
            db.select(
                db.literal("bill"),
                db.func.max(Sale.bill_offer_name),
                db.func.count(Sale.id),
                db.func.sum(Sale.bill_offer_discount),
            )
            .where(*paid, Sale.bill_offer_id.is_not(None))
            .group_by(Sale.bill_offer_id)
        )
        manual = (
            db.select(
                db.literal("manual"),
                db.literal("Manual discounts"),
                db.func.count(db.distinct(SaleItem.sale_id)),
                db.func.sum(SaleItem.manual_discount),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*paid, SaleItem.manual_discount > 0)
            .having(db.func.count(SaleItem.id) > 0)
        )
        rows = [*db.session.execute(item).all(), *db.session.execute(bill).all(), *db.session.execute(manual).all()]
        return sorted(rows, key=lambda r: r[3], reverse=True)

    def shifts(self, store_id: int | None, start: datetime, end: datetime):
        """Shifts opened in the range, with bill count and cash taken."""
        paid = (
            db.select(
                Sale.shift_id,
                db.func.count(db.distinct(Sale.id)).label("bills"),
                db.func.coalesce(
                    db.func.sum(Payment.amount).filter(Payment.method == PaymentMethod.CASH), 0
                ).label("cash_sales"),
            )
            .join(Payment, Payment.sale_id == Sale.id)
            .where(Sale.status == SaleStatus.PAID)
            .group_by(Sale.shift_id)
            .subquery()
        )
        q = (
            db.select(
                CashierShift,
                User.full_name,
                Counter.code,
                db.func.coalesce(paid.c.bills, 0),
                db.func.coalesce(paid.c.cash_sales, 0),
            )
            .join(User, User.id == CashierShift.user_id)
            .outerjoin(Counter, Counter.id == CashierShift.counter_id)
            .outerjoin(paid, paid.c.shift_id == CashierShift.id)
            .where(CashierShift.opened_at >= start, CashierShift.opened_at < end)
            .order_by(CashierShift.opened_at.desc())
        )
        if store_id is not None:
            q = q.where(CashierShift.store_id == store_id)
        return db.session.execute(q).all()

    def open_shift_count(self, store_id: int | None) -> int:
        q = db.select(db.func.count(CashierShift.id)).where(CashierShift.status == ShiftStatus.OPEN)
        if store_id is not None:
            q = q.where(CashierShift.store_id == store_id)
        return db.session.scalar(q) or 0

    def recent_sales(self, store_id: int | None, limit: int = 10):
        q = (
            db.select(Sale, User.full_name)
            .join(User, User.id == Sale.cashier_id)
            .where(Sale.status == SaleStatus.PAID)
            .order_by(Sale.completed_at.desc())
            .limit(limit)
        )
        if store_id is not None:
            q = q.where(Sale.store_id == store_id)
        return db.session.execute(q).all()
