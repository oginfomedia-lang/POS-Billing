"""Report logic on top of report_repository."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from app.models.enums import ShiftStatus
from app.repositories.report_repository import ReportRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.report_schemas import (
    BillListOut,
    BillListQuery,
    BillRow,
    CollectionReportOut,
    CollectionRow,
    CollectionTotals,
    DailyRow,
    DashboardOut,
    GstHsnRow,
    GstRow,
    ListTotals,
    MethodRow,
    OfferRow,
    ProfitCategoryRow,
    ProfitReportOut,
    ProfitRow,
    ProfitSummary,
    RecentSale,
    ReportQuery,
    ReturnListOut,
    ReturnListRow,
    SalesReportOut,
    SalesSummary,
    ShiftRow,
    TopProductRow,
    UncostedRow,
)
from app.services import inventory_service, pricing_service
from app.utils.dates import IST, business_date
from app.utils.money import round_money
from app.utils.phone import mask_mobile


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


def _trim_qty(qty: Decimal) -> Decimal:
    """3.000 -> 3, 2.500 -> 2.5 (normalize() alone would turn 100 into 1E+2)."""
    return qty.quantize(Decimal(1)) if qty == qty.to_integral_value() else qty.normalize()


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
            TopProductRow(product_id=pid, product_name=name, qty=_trim_qty(qty), amount=amt)
            for pid, name, qty, amt in repo.top_products(q.store_id, start, end)
        ],
        offers=[
            OfferRow(kind=k, name=n, bills=b, amount=a)
            for k, n, b, a in repo.offer_usage(q.store_id, start, end)
        ],
    )


def _margin(profit: Decimal, sales: Decimal) -> Decimal | None:
    return round_money(profit * 100 / sales) if sales else None


def profit_report(q: ReportQuery) -> ProfitReportOut:
    """Gross profit: sales minus returns (before GST) against the purchase cost of what was sold."""
    d_from, d_to, start, end = _range(q)
    repo = ReportRepository()
    zero = Decimal("0")
    # product_id -> [name, category, qty, net, cogs, uncosted_qty, uncosted_net]; returns are subtracted.
    lines: dict[int, list] = {}
    returns = zero
    for sign, rows in ((1, repo.profit_sales(q.store_id, start, end)), (-1, repo.profit_returns(q.store_id, start, end))):
        for pid, name, category, *nums in rows:
            row = lines.setdefault(pid, [name, category, zero, zero, zero, zero, zero])
            for i, n in enumerate(nums):
                row[2 + i] += sign * Decimal(n)
            if sign < 0:
                returns += Decimal(nums[1])

    products: list[ProfitRow] = []
    uncosted: list[UncostedRow] = []
    categories: dict[str | None, list[Decimal]] = {}
    for pid, (name, category, qty, net, cogs, u_qty, u_net) in lines.items():
        if u_qty or u_net:
            uncosted.append(UncostedRow(
                product_id=pid, product_name=name, qty=_trim_qty(u_qty), net_sales=round_money(u_net),
            ))
        sales, cost = round_money(net - u_net), round_money(cogs)
        if qty == u_qty and not sales and not cost:
            continue  # nothing with a known cost
        profit = sales - cost
        products.append(ProfitRow(
            product_id=pid, product_name=name, category=category, qty=_trim_qty(qty - u_qty),
            net_sales=sales, cogs=cost, gross_profit=profit, margin_pct=_margin(profit, sales),
        ))
        cat = categories.setdefault(category, [zero, zero])
        cat[0] += sales
        cat[1] += cost
    products.sort(key=lambda r: r.gross_profit, reverse=True)
    uncosted.sort(key=lambda r: r.net_sales, reverse=True)

    costed = sum((r.net_sales for r in products), zero)
    cogs = sum((r.cogs for r in products), zero)
    unc = sum((r.net_sales for r in uncosted), zero)
    return ProfitReportOut(
        store_id=q.store_id,
        date_from=d_from,
        date_to=d_to,
        summary=ProfitSummary(
            net_sales=costed + unc, returns=round_money(returns), costed_sales=costed, cogs=cogs,
            gross_profit=costed - cogs, margin_pct=_margin(costed - cogs, costed),
            uncosted_sales=unc, uncosted_products=len(uncosted),
        ),
        by_category=sorted(
            (ProfitCategoryRow(category=c, net_sales=s, cogs=k, gross_profit=s - k, margin_pct=_margin(s - k, s))
             for c, (s, k) in categories.items()),
            key=lambda r: r.gross_profit, reverse=True,
        ),
        products=products,
        uncosted=uncosted,
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


# The dashboard's expiry alert counts what Stock / Inventory → Expiry alerts lists.
NEAR_EXPIRY_DAYS = 30


def _pages(total: int, per_page: int) -> int:
    return max(1, -(-total // per_page))


def bill_list(q: BillListQuery) -> BillListOut:
    """The bills behind the sales tiles (same dates, store and PAID rule), with totals for the filter."""
    d_from, d_to, start, end = _range(q)
    rows, t = ReportRepository().list_bills(
        q.store_id, start, end, q.status, q.method, q.discounted, (q.q or "").strip() or None, q.page, q.per_page,
    )
    refunded = ReturnRepository().refunded_by_sale([s.id for s, _, _ in rows])
    items = [
        BillRow(
            id=s.id, bill_number=s.bill_number, status=s.status.value,
            at=s.completed_at if q.status == "paid" else s.updated_at,
            cashier_name=cashier, counter_code=counter, items_count=len(s.items),
            customer_mobile=mask_mobile(s.customer_mobile),
            subtotal=s.subtotal, discount=s.discount_amount, tax=s.tax_amount, total=s.total,
            methods=list(dict.fromkeys(p.method for p in s.payments)),
            refunded=refunded.get(s.id, (0, Decimal("0")))[1],
        )
        for s, cashier, counter in rows
    ]
    return BillListOut(
        date_from=d_from, date_to=d_to, items=items,
        totals=ListTotals(count=t.count, subtotal=t.subtotal, discount=t.discount, tax=t.tax, total=t.total),
        page=q.page, per_page=q.per_page, pages=_pages(t.count, q.per_page),
    )


def return_list(q: BillListQuery) -> ReturnListOut:
    """Refunds (credit notes) paid in the period, as counted by the sales report's Returns tile."""
    d_from, d_to, start, end = _range(q)
    rows, t = ReportRepository().list_returns(q.store_id, start, end, q.page, q.per_page)
    items = [
        ReturnListRow(
            id=r.id, return_number=r.return_number, created_at=r.created_at,
            bill_number=r.sale.bill_number if r.sale else None, sale_id=r.sale_id,
            cashier_name=r.cashier.full_name if r.cashier else "", approved_by_name=r.approved_by.full_name if r.approved_by else "",
            reason=r.reason, refund_method=r.refund_method, refund_amount=r.refund_amount, items_count=len(r.items),
        )
        for r in rows
    ]
    return ReturnListOut(
        date_from=d_from, date_to=d_to, items=items, totals=ListTotals(count=t.count, total=t.total),
        page=q.page, per_page=q.per_page, pages=_pages(t.count, q.per_page),
    )


def dashboard(store_id: int | None) -> DashboardOut:
    repo = ReportRepository()
    today, _, start, end = _range(ReportQuery())
    if store_id is not None:
        store_ids = [store_id]
    else:
        stores, _ = StoreRepository().list(per_page=1000, active_only=True)
        store_ids = [s.id for s in stores]
    low_stock = sum(1 for sid in store_ids for lv in inventory_service.stock_levels(sid) if lv.is_low)
    near_expiry = sum(len(inventory_service.expiring_soon(sid, NEAR_EXPIRY_DAYS)) for sid in store_ids)
    return DashboardOut(
        store_id=store_id,
        date=today,
        summary=_summary(repo, store_id, start, end),
        by_method=_methods(repo, store_id, start, end),
        open_shifts=repo.open_shift_count(store_id),
        low_stock=low_stock,
        near_expiry=near_expiry,
        recent_sales=[
            RecentSale(id=s.id, bill_number=s.bill_number, cashier_name=name, total=s.total, completed_at=s.completed_at)
            for s, name in repo.recent_sales(store_id)
        ],
    )
