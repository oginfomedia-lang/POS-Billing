"""Aggregate SQL for reports (sales, GST, shifts, low stock).

All sales figures count PAID bills only, by completed_at in [start, end). Returns (credit notes) count
by the day the cash went out (SaleReturn.created_at). store_id=None means all stores.
"""
from datetime import datetime

from app.extensions import db
from app.models.category import Category
from app.models.enums import PaymentMethod, SaleStatus, ShiftStatus
from app.models.inventory import Inventory
from app.models.payment import Payment
from app.models.product import Product
from app.models.returns import SaleReturn, SaleReturnItem
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

    def _returned(self, store_id: int | None, start: datetime, end: datetime) -> list:
        conds = [SaleReturn.created_at >= start, SaleReturn.created_at < end]
        if store_id is not None:
            conds.append(SaleReturn.store_id == store_id)
        return conds

    def refunds_summary(self, store_id: int | None, start: datetime, end: datetime):
        """(returns, refunded): number of returns and cash given back (incl. GST)."""
        f = db.func
        q = db.select(
            f.count(SaleReturn.id).label("returns"),
            f.coalesce(f.sum(SaleReturn.refund_amount), 0).label("refunded"),
        ).where(*self._returned(store_id, start, end))
        return db.session.execute(q).one()

    def refunds_gst_by_rate(self, store_id: int | None, start: datetime, end: datetime):
        q = (
            db.select(
                SaleReturnItem.tax_rate,
                db.func.sum(SaleReturnItem.line_total - SaleReturnItem.discount_amount),
                db.func.sum(SaleReturnItem.tax_amount),
            )
            .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
            .where(*self._returned(store_id, start, end))
            .group_by(SaleReturnItem.tax_rate)
        )
        return db.session.execute(q).all()

    def refunds_gst_by_hsn(self, store_id: int | None, start: datetime, end: datetime):
        q = (
            db.select(
                SaleReturnItem.hsn_code,
                SaleReturnItem.tax_rate,
                db.func.sum(SaleReturnItem.line_total - SaleReturnItem.discount_amount),
                db.func.sum(SaleReturnItem.tax_amount),
            )
            .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id)
            .where(*self._returned(store_id, start, end))
            .group_by(SaleReturnItem.hsn_code, SaleReturnItem.tax_rate)
        )
        return db.session.execute(q).all()

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

    def gst_by_hsn(self, store_id: int | None, start: datetime, end: datetime):
        """(hsn_code, tax_rate, taxable, tax) — HSN-wise summary for GST returns. hsn_code None = not set."""
        q = (
            db.select(
                SaleItem.hsn_code,
                SaleItem.tax_rate,
                db.func.sum(SaleItem.line_total - SaleItem.discount_amount).label("taxable"),
                db.func.sum(SaleItem.tax_amount).label("tax"),
            )
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(*self._paid(store_id, start, end))
            .group_by(SaleItem.hsn_code, SaleItem.tax_rate)
            .order_by(SaleItem.hsn_code.nulls_last(), SaleItem.tax_rate)
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

    @staticmethod
    def _profit_lines(item, store_col, conds, join):
        """(product_id, name, category, qty, net, cogs, uncosted_qty, uncosted_net) per product.

        net = line_total - discount (before GST). Cost = the cost saved on the line, else (bills from before
        costs were kept) the product's current cost in that store. Lines with no cost at all are counted in
        uncosted_* and left out of cogs.
        """
        f = db.func
        cost = f.coalesce(item.unit_cost, Inventory.avg_cost, Product.cost_price)
        net = item.line_total - item.discount_amount
        no_cost = cost.is_(None)
        q = (
            db.select(
                item.product_id,
                f.max(item.product_name),
                f.max(Category.name),
                f.sum(item.qty),
                f.sum(net),
                f.coalesce(f.sum(item.qty * cost), 0),
                f.coalesce(f.sum(db.case((no_cost, item.qty), else_=0)), 0),
                f.coalesce(f.sum(db.case((no_cost, net), else_=0)), 0),
            )
            .join(*join)
            .join(Product, Product.id == item.product_id)
            .outerjoin(Category, Category.id == Product.category_id)
            .outerjoin(Inventory, (Inventory.product_id == item.product_id) & (Inventory.store_id == store_col))
            .where(*conds)
            .group_by(item.product_id)
        )
        return db.session.execute(q).all()

    def profit_sales(self, store_id: int | None, start: datetime, end: datetime):
        return self._profit_lines(
            SaleItem, Sale.store_id, self._paid(store_id, start, end), (Sale, Sale.id == SaleItem.sale_id)
        )

    def profit_returns(self, store_id: int | None, start: datetime, end: datetime):
        return self._profit_lines(
            SaleReturnItem, SaleReturn.store_id, self._returned(store_id, start, end),
            (SaleReturn, SaleReturn.id == SaleReturnItem.return_id),
        )

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
        refunds = (
            db.select(
                SaleReturn.shift_id,
                db.func.sum(SaleReturn.refund_amount)
                .filter(SaleReturn.refund_method == PaymentMethod.CASH)
                .label("cash_refunds"),
            )
            .group_by(SaleReturn.shift_id)
            .subquery()
        )
        q = (
            db.select(
                CashierShift,
                User.full_name,
                Counter.code,
                db.func.coalesce(paid.c.bills, 0),
                db.func.coalesce(paid.c.cash_sales, 0),
                db.func.coalesce(refunds.c.cash_refunds, 0),
            )
            .join(User, User.id == CashierShift.user_id)
            .outerjoin(Counter, Counter.id == CashierShift.counter_id)
            .outerjoin(paid, paid.c.shift_id == CashierShift.id)
            .outerjoin(refunds, refunds.c.shift_id == CashierShift.id)
            .where(CashierShift.opened_at >= start, CashierShift.opened_at < end)
            .order_by(CashierShift.opened_at.desc())
        )
        if store_id is not None:
            q = q.where(CashierShift.store_id == store_id)
        return db.session.execute(q).all()

    def collection_by_cashier(self, store_id: int | None, start: datetime, end: datetime):
        """(cashier_id, counter_id, bills, cash, card, upi, total) for paid bills, per cashier and counter."""
        f = db.func

        def by(method: PaymentMethod):
            return f.coalesce(f.sum(Payment.amount).filter(Payment.method == method), 0)

        q = (
            db.select(
                Sale.cashier_id,
                Sale.counter_id,
                f.count(db.distinct(Sale.id)),
                by(PaymentMethod.CASH),
                by(PaymentMethod.CARD),
                by(PaymentMethod.UPI),
                f.coalesce(f.sum(Payment.amount), 0),
            )
            .outerjoin(Payment, Payment.sale_id == Sale.id)
            .where(*self._paid(store_id, start, end))
            .group_by(Sale.cashier_id, Sale.counter_id)
        )
        return db.session.execute(q).all()

    def refunds_by_cashier(self, store_id: int | None, start: datetime, end: datetime):
        """(cashier_id, counter_id, refunded): cash given back, on the counter of the shift that paid it out."""
        q = (
            db.select(SaleReturn.cashier_id, CashierShift.counter_id, db.func.sum(SaleReturn.refund_amount))
            .join(CashierShift, CashierShift.id == SaleReturn.shift_id)
            .where(*self._returned(store_id, start, end))
            .group_by(SaleReturn.cashier_id, CashierShift.counter_id)
        )
        return db.session.execute(q).all()

    def shifts_for_collection(self, store_id: int | None, start: datetime, end: datetime) -> list[CashierShift]:
        """Shifts closed in the range (for cash short/over) and shifts still open (numbers may still change)."""
        q = db.select(CashierShift).where(
            db.or_(
                db.and_(CashierShift.closed_at >= start, CashierShift.closed_at < end),
                db.and_(CashierShift.status == ShiftStatus.OPEN, CashierShift.opened_at < end),
            )
        )
        if store_id is not None:
            q = q.where(CashierShift.store_id == store_id)
        return list(db.session.scalars(q).all())

    def names(self, user_ids: set[int], counter_ids: set[int]) -> tuple[dict[int, str], dict[int, str]]:
        """({user_id: full_name}, {counter_id: code})."""
        users = dict(db.session.execute(db.select(User.id, User.full_name).where(User.id.in_(user_ids))).all()) if user_ids else {}
        counters = dict(db.session.execute(db.select(Counter.id, Counter.code).where(Counter.id.in_(counter_ids))).all()) if counter_ids else {}
        return users, counters

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

    # ── Bill / return lists ──────────────────────────────────────────────────────────

    def _bill_conditions(self, store_id, start, end, status, method, discounted, text) -> list:
        if status == "voided":  # same rule as voided_count()
            conds = [Sale.status == SaleStatus.VOIDED, Sale.updated_at >= start, Sale.updated_at < end]
            if store_id is not None:
                conds.append(Sale.store_id == store_id)
        else:
            conds = self._paid(store_id, start, end)
        if method is not None:
            conds.append(Sale.id.in_(db.select(Payment.sale_id).where(Payment.method == method)))
        if discounted:
            conds.append(Sale.discount_amount > 0)
        if text:
            conds.append(Sale.bill_number.icontains(text, autoescape=True))
        return conds

    def list_bills(self, store_id, start, end, status, method, discounted, text, page, per_page):
        """(rows of (Sale, cashier name, counter code), totals row) — newest first."""
        conds = self._bill_conditions(store_id, start, end, status, method, discounted, text)
        f = db.func
        totals = db.session.execute(
            db.select(
                f.count(Sale.id).label("count"),
                f.coalesce(f.sum(Sale.subtotal), 0).label("subtotal"),
                f.coalesce(f.sum(Sale.discount_amount), 0).label("discount"),
                f.coalesce(f.sum(Sale.tax_amount), 0).label("tax"),
                f.coalesce(f.sum(Sale.total), 0).label("total"),
            ).where(*conds)
        ).one()
        when = Sale.updated_at if status == "voided" else Sale.completed_at
        rows = db.session.execute(
            db.select(Sale, User.full_name, Counter.code)
            .join(User, User.id == Sale.cashier_id)
            .outerjoin(Counter, Counter.id == Sale.counter_id)
            .where(*conds)
            .order_by(when.desc(), Sale.id.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return rows, totals

    def list_returns(self, store_id, start, end, page, per_page):
        """(rows of SaleReturn, totals row) — newest first, by the day the refund was paid."""
        conds = self._returned(store_id, start, end)
        f = db.func
        totals = db.session.execute(
            db.select(f.count(SaleReturn.id).label("count"),
                      f.coalesce(f.sum(SaleReturn.refund_amount), 0).label("total")).where(*conds)
        ).one()
        rows = db.session.scalars(
            db.select(SaleReturn).where(*conds)
            .order_by(SaleReturn.created_at.desc(), SaleReturn.id.desc())
            .offset((page - 1) * per_page).limit(per_page)
        ).all()
        return list(rows), totals
