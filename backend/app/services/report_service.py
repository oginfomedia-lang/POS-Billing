"""Report logic on top of report_repository."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.repositories.report_repository import ReportRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.report_schemas import (
    DailyRow,
    DashboardOut,
    GstRow,
    MethodRow,
    RecentSale,
    ReportQuery,
    SalesReportOut,
    SalesSummary,
    ShiftRow,
    TopProductRow,
)
from app.services import inventory_service
from app.utils.dates import IST, business_date
from app.utils.money import round_money


def _range(q: ReportQuery) -> tuple[date, date, datetime, datetime]:
    """Inclusive IST dates -> [start, end) timestamps."""
    today = business_date()
    d_from = q.date_from or q.date_to or today
    d_to = q.date_to or d_from
    start = datetime.combine(d_from, time.min, IST)
    end = datetime.combine(d_to + timedelta(days=1), time.min, IST)
    return d_from, d_to, start, end


def _summary(repo: ReportRepository, store_id: int | None, start: datetime, end: datetime) -> SalesSummary:
    row = repo.summary(store_id, start, end)
    total = Decimal(row.total)
    return SalesSummary(
        bills=row.bills,
        voided=repo.voided_count(store_id, start, end),
        subtotal=row.subtotal,
        discount=row.discount,
        tax=row.tax,
        total=total,
        average_bill=round_money(total / row.bills) if row.bills else Decimal("0.00"),
    )


def _methods(repo: ReportRepository, store_id: int | None, start: datetime, end: datetime) -> list[MethodRow]:
    return [MethodRow(method=m, bills=b, amount=a) for m, b, a in repo.by_payment_method(store_id, start, end)]


def sales_report(q: ReportQuery) -> SalesReportOut:
    repo = ReportRepository()
    d_from, d_to, start, end = _range(q)
    gst = []
    for rate, taxable, tax in repo.gst_by_rate(q.store_id, start, end):
        cgst = round_money(Decimal(tax) / 2)
        gst.append(GstRow(tax_rate=rate, taxable=taxable, tax=tax, cgst=cgst, sgst=Decimal(tax) - cgst))
    return SalesReportOut(
        store_id=q.store_id,
        date_from=d_from,
        date_to=d_to,
        summary=_summary(repo, q.store_id, start, end),
        by_method=_methods(repo, q.store_id, start, end),
        daily=[DailyRow(day=d, bills=b, total=t) for d, b, t in repo.daily(q.store_id, start, end)],
        gst=gst,
        top_products=[
            TopProductRow(product_id=pid, product_name=name, qty=qty, amount=amt)
            for pid, name, qty, amt in repo.top_products(q.store_id, start, end)
        ],
    )


def shift_report(q: ReportQuery) -> list[ShiftRow]:
    _, _, start, end = _range(q)
    rows = []
    for shift, cashier, counter_code, bills, cash_sales in ReportRepository().shifts(q.store_id, start, end):
        expected = shift.expected_cash
        diff = shift.actual_cash - expected if expected is not None and shift.actual_cash is not None else None
        rows.append(ShiftRow(
            id=shift.id,
            cashier_name=cashier,
            counter_code=counter_code,
            status=shift.status.value,
            opened_at=shift.opened_at,
            closed_at=shift.closed_at,
            opening_float=shift.opening_float,
            bills=bills,
            cash_sales=cash_sales,
            expected_cash=expected,
            actual_cash=shift.actual_cash,
            difference=diff,
        ))
    return rows


def dashboard(store_id: int | None) -> DashboardOut:
    repo = ReportRepository()
    today, _, start, end = _range(ReportQuery())
    if store_id is not None:
        low_stock = sum(1 for lv in inventory_service.stock_levels(store_id) if lv.is_low)
    else:
        stores, _ = StoreRepository().list(per_page=1000, active_only=True)
        low_stock = sum(1 for s in stores for lv in inventory_service.stock_levels(s.id) if lv.is_low)
    return DashboardOut(
        store_id=store_id,
        date=today,
        summary=_summary(repo, store_id, start, end),
        by_method=_methods(repo, store_id, start, end),
        open_shifts=repo.open_shift_count(store_id),
        low_stock=low_stock,
        recent_sales=[
            RecentSale(id=s.id, bill_number=s.bill_number, cashier_name=name, total=s.total, completed_at=s.completed_at)
            for s, name in repo.recent_sales(store_id)
        ],
    )
