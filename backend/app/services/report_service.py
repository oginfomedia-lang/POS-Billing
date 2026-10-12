"""Report logic on top of report_repository."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.models.enums import ShiftStatus
from app.repositories.report_repository import ReportRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.report_schemas import (
    CollectionReportOut,
    CollectionRow,
    CollectionTotals,
    DailyRow,
    DashboardOut,
    GstHsnRow,
    GstRow,
    MethodRow,
    OfferRow,
    RecentSale,
    ReportQuery,
    SalesReportOut,
    SalesSummary,
    ShiftRow,
    TopProductRow,
)
from app.services import inventory_service, pricing_service
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
    refunds = repo.refunds_summary(store_id, start, end)
    return SalesSummary(
        bills=row.bills,
        voided=repo.voided_count(store_id, start, end),
        subtotal=row.subtotal,
        discount=row.discount,
        tax=row.tax,
        total=total,
        average_bill=round_money(total / row.bills) if row.bills else Decimal("0.00"),
        returns=refunds.returns,
        refunded=refunds.refunded,
        net_total=total - Decimal(refunds.refunded),
    )


def _net(sales_rows, refund_rows) -> list[tuple]:
    """GST rows minus returned GST rows with the same key: (rate,) or (hsn, rate) -> [(*key, taxable, tax)]."""
    out: dict[tuple, list[Decimal]] = {}
    for *key, taxable, tax in sales_rows:
        out[tuple(key)] = [Decimal(taxable), Decimal(tax)]
    for *key, taxable, tax in refund_rows:
        row = out.setdefault(tuple(key), [Decimal("0"), Decimal("0")])
        row[0] -= Decimal(taxable)
        row[1] -= Decimal(tax)
    rows = [(*k, v[0], v[1]) for k, v in out.items()]
    # No-HSN rows last, then by HSN / rate.
    return sorted(rows, key=lambda r: tuple((x is None, x if x is not None else 0) for x in r[:-2]))


def _methods(repo: ReportRepository, store_id: int | None, start: datetime, end: datetime) -> list[MethodRow]:
    return [MethodRow(method=m, bills=b, amount=a) for m, b, a in repo.by_payment_method(store_id, start, end)]


def sales_report(q: ReportQuery) -> SalesReportOut:
    repo = ReportRepository()
    d_from, d_to, start, end = _range(q)
    # GST is reported net of returns (credit notes) in the same period.
    gst = []
    by_rate = _net(repo.gst_by_rate(q.store_id, start, end), repo.refunds_gst_by_rate(q.store_id, start, end))
    for rate, taxable, tax in by_rate:
        cgst, sgst = pricing_service.split_gst(tax)
        gst.append(GstRow(tax_rate=rate, taxable=taxable, tax=tax, cgst=cgst, sgst=sgst))
    gst_hsn = []
    by_hsn = _net(repo.gst_by_hsn(q.store_id, start, end), repo.refunds_gst_by_hsn(q.store_id, start, end))
    for hsn, rate, taxable, tax in by_hsn:
        cgst, sgst = pricing_service.split_gst(tax)
        gst_hsn.append(GstHsnRow(hsn_code=hsn, tax_rate=rate, taxable=taxable, tax=tax, cgst=cgst, sgst=sgst))
    return SalesReportOut(
        store_id=q.store_id,
        date_from=d_from,
        date_to=d_to,
        summary=_summary(repo, q.store_id, start, end),
        by_method=_methods(repo, q.store_id, start, end),
        daily=[DailyRow(day=d, bills=b, total=t) for d, b, t in repo.daily(q.store_id, start, end)],
        gst=gst,
        gst_hsn=gst_hsn,
        top_products=[
            TopProductRow(product_id=pid, product_name=name, qty=qty, amount=amt)
            for pid, name, qty, amt in repo.top_products(q.store_id, start, end)
        ],
        offers=[
            OfferRow(kind=k, name=n, bills=b, amount=a)
            for k, n, b, a in repo.offer_usage(q.store_id, start, end)
        ],
    )


def shift_report(q: ReportQuery) -> list[ShiftRow]:
    _, _, start, end = _range(q)
    rows = []
    for shift, cashier, counter_code, bills, cash_sales, cash_refunds in ReportRepository().shifts(
        q.store_id, start, end
    ):
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
            cash_refunds=cash_refunds,
            expected_cash=expected,
            actual_cash=shift.actual_cash,
            difference=diff,
        ))
    return rows


def collection_report(q: ReportQuery) -> CollectionReportOut:
    """Money collected per (cashier, counter): payment split, refunds, net, and cash short/over."""
    repo = ReportRepository()
    d_from, d_to, start, end = _range(q)
    rows: dict[tuple[int, int | None], dict] = {}

    def row(cashier_id: int, counter_id: int | None) -> dict:
        return rows.setdefault((cashier_id, counter_id), {"bills": 0})

    for cashier_id, counter_id, bills, cash, card, upi, total in repo.collection_by_cashier(q.store_id, start, end):
        row(cashier_id, counter_id).update(
            bills=bills, cash=round_money(cash), card=round_money(card), upi=round_money(upi), total=round_money(total)
        )
    for cashier_id, counter_id, refunded in repo.refunds_by_cashier(q.store_id, start, end):
        row(cashier_id, counter_id)["refunds"] = round_money(refunded)
    for shift in repo.shifts_for_collection(q.store_id, start, end):
        r = row(shift.user_id, shift.counter_id)
        if shift.status == ShiftStatus.OPEN:
            r["shift_open"] = True
        elif shift.expected_cash is not None and shift.actual_cash is not None:
            r["cash_difference"] = r.get("cash_difference", Decimal("0")) + shift.actual_cash - shift.expected_cash

    users, counters = repo.names({k[0] for k in rows}, {k[1] for k in rows if k[1] is not None})
    out = []
    for (cashier_id, counter_id), r in rows.items():
        item = CollectionRow(
            cashier_id=cashier_id, cashier_name=users.get(cashier_id, "?"), counter_code=counters.get(counter_id), **r
        )
        item.net = item.total - item.refunds
        out.append(item)
    out.sort(key=lambda r: (-r.net, r.cashier_name))

    def total(field: str):
        return sum((getattr(r, field) for r in out), Decimal("0.00"))

    return CollectionReportOut(
        store_id=q.store_id,
        date_from=d_from,
        date_to=d_to,
        rows=out,
        totals=CollectionTotals(
            bills=sum(r.bills for r in out),
            **{f: total(f) for f in ("cash", "card", "upi", "total", "refunds", "net")},
        ),
    )


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
