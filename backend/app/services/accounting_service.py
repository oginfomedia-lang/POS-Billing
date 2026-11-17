"""Accounting vouchers for Tally, built fresh from the POS records each time (nothing extra is stored, so the books
can never drift from the bills).

- Sales: one voucher per store per day. Debit: what came in, by payment mode (Cash / UPI / Card ledgers; bills
  sold on udhari go to the Udhari customers ledger, a Sundry Debtor).
  Credit: the sales ledger per GST rate (value after discounts, before GST) and Output CGST / SGST per rate.
- Sales returns (credit notes): one voucher per store per day, the other way round; credit the refund mode
  (a return from an udhari bill credits the Udhari ledger: it came off the khata).
- Udhari paid back (receipt): one voucher per repayment; debit Cash / UPI / Card / Bank, credit Udhari.
- Supplier invoices (purchase): debit the purchase ledger per GST rate, Input GST (IGST when the supplier is in
  another state), the bill's other charges; credit the supplier with what is payable (= goods received). If the
  shop pays less than the goods' value, the gap goes to Round Off.
- Supplier payments and advances (payment): debit the supplier, credit Cash or Bank.
- Goods sent back to the supplier (debit note): debit the supplier, credit purchase return and Input GST.

Every voucher's debits equal its credits; any paisa left over goes to Round Off, with a warning.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models.customer import CreditTransaction
from app.models.enums import (
    CreditTxnType,
    PaymentMethod,
    SaleStatus,
    SupplierInvoiceStatus,
    SupplierPaymentMethod,
    SupplierPaymentType,
)
from app.models.payment import Payment
from app.models.purchase import GoodsReceiptItem
from app.models.returns import SaleReturn, SaleReturnItem
from app.models.sale import Sale, SaleItem
from app.models.store import Store
from app.models.supplier_invoice import SupplierInvoice
from app.models.supplier_payment import SupplierPayment
from app.models.supplier_return import SupplierReturn
from app.models.user import User
from app.repositories.settings_repository import SettingsRepository
from app.schemas.accounting_schemas import (
    DayBookOut,
    GstHeadRow,
    GstSummaryOut,
    TallyLedgers,
    Voucher,
    VoucherLine,
    VoucherOut,
)
from app.services import audit_service, pricing_service, purchase_service
from app.utils.dates import IST
from app.utils.money import round_money
from app.utils.transactions import transaction

ZERO = Decimal("0")
IST_ZONE = "Asia/Kolkata"
_KEY = "tally_"  # system_settings keys: tally_cash, tally_sales, ...


# ── Ledger names ─────────────────────────────────────────────────────────────

def get_ledgers() -> TallyLedgers:
    saved = SettingsRepository().all()
    known = {k[len(_KEY):]: v for k, v in saved.items() if k.startswith(_KEY) and k[len(_KEY):] in TallyLedgers.model_fields}
    return TallyLedgers.model_validate(known)


def update_ledgers(data: TallyLedgers, actor: User) -> TallyLedgers:
    old = get_ledgers().model_dump()
    new = data.model_dump()
    repo = SettingsRepository()
    with transaction():
        for key, value in new.items():
            repo.upsert(_KEY + key, value, actor.id)
        changed = {k for k in new if new[k] != old[k]}
        if changed:
            audit_service.log(actor, "accounting.ledgers", "settings", None,
                              {k: old[k] for k in changed}, {k: new[k] for k in changed})
    return get_ledgers()


def _rate_text(rate: Decimal) -> str:
    """5.00 → "5", 2.50 → "2.5"."""
    text = f"{Decimal(rate).normalize():f}"
    return text if text != "-0" else "0"


def _name(template: str, rate) -> str:
    rate = Decimal(str(rate))
    return template.replace("{rate}", _rate_text(rate)).replace("{half}", _rate_text(rate / 2))


# ── Building vouchers ────────────────────────────────────────────────────────

class _Lines:
    """Debits and credits by ledger, in the order first used; the same ledger on both sides is netted."""

    def __init__(self) -> None:
        self._amounts: dict[str, Decimal] = {}  # + debit, − credit

    def dr(self, ledger: str, amount) -> None:
        amount = round_money(amount)
        if amount:
            self._amounts[ledger] = self._amounts.get(ledger, ZERO) + amount

    def cr(self, ledger: str, amount) -> None:
        self.dr(ledger, -round_money(amount))

    def finish(self, round_off: str, what: str, warnings: list[str]) -> list[VoucherLine]:
        gap = sum(self._amounts.values(), ZERO)
        if gap:
            self.cr(round_off, gap)
            if abs(gap) > Decimal("0.05"):
                warnings.append(f"{what}: debit and credit differed by ₹{abs(gap)}; put to {round_off}.")
        return [
            VoucherLine(ledger=ledger, debit=amt if amt > 0 else ZERO, credit=-amt if amt < 0 else ZERO)
            for ledger, amt in self._amounts.items() if amt
        ]


def _gst_lines(lines: _Lines, side: str, rate, tax, *, interstate: bool, cgst: str, sgst: str, igst: str | None) -> None:
    post = lines.dr if side == "dr" else lines.cr
    if interstate and igst:
        post(_name(igst, rate), tax)
    else:
        c, s = pricing_service.split_gst(tax)
        post(_name(cgst, rate), c)
        post(_name(sgst, rate), s)


def _range(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    return datetime.combine(date_from, time.min, IST), datetime.combine(date_to + timedelta(days=1), time.min, IST)


def _stores() -> dict[int, Store]:
    return {s.id: s for s in db.session.scalars(select(Store)).all()}


def _state(gstin: str | None) -> str | None:
    """The state code: the first two digits of a GSTIN."""
    gstin = (gstin or "").strip()
    return gstin[:2] if len(gstin) >= 2 and gstin[:2].isdigit() else None


def _interstate(store: Store | None, supplier) -> bool:
    ours, theirs = _state(store.gstin if store else None), _state(supplier.gstin if supplier else None)
    return bool(ours and theirs and ours != theirs)


def _mode_ledger(method, led: TallyLedgers) -> str:
    """The ledger money moved through. "credit" = udhari: nothing was received, the customer owes it."""
    value = method.value if hasattr(method, "value") else str(method)
    ledgers = {"cash": led.cash, "upi": led.upi, "card": led.card, "bank": led.bank, "credit": led.udhari}
    return ledgers.get(value, led.cash)


def _udhari_repayments(store_id: int | None, start: datetime, end: datetime) -> list[CreditTransaction]:
    q = (
        select(CreditTransaction)
        .where(CreditTransaction.txn_type == CreditTxnType.PAYMENT)
        .where(CreditTransaction.created_at >= start, CreditTransaction.created_at < end)
        .order_by(CreditTransaction.created_at, CreditTransaction.id)
    )
    if store_id is not None:
        q = q.where(CreditTransaction.store_id == store_id)
    return list(db.session.scalars(q).all())


# Sales and returns: summed in SQL per store and day (a year can have lakhs of bills).

def _sales_days(store_id: int | None, start: datetime, end: datetime):
    day = db.func.date(db.func.timezone(IST_ZONE, Sale.completed_at)).label("day")
    conds = [Sale.status == SaleStatus.PAID, Sale.completed_at >= start, Sale.completed_at < end]
    if store_id is not None:
        conds.append(Sale.store_id == store_id)
    rates = db.session.execute(
        select(Sale.store_id, day, SaleItem.tax_rate,
               db.func.sum(SaleItem.line_total - SaleItem.discount_amount), db.func.sum(SaleItem.tax_amount))
        .join(Sale, Sale.id == SaleItem.sale_id).where(*conds)
        .group_by(Sale.store_id, day, SaleItem.tax_rate)
    ).all()
    modes = db.session.execute(
        select(Sale.store_id, day, Payment.method, db.func.sum(Payment.amount))
        .join(Sale, Sale.id == Payment.sale_id).where(*conds)
        .group_by(Sale.store_id, day, Payment.method)
    ).all()
    bills = db.session.execute(
        select(Sale.store_id, day, db.func.count(Sale.id), db.func.min(Sale.bill_number), db.func.max(Sale.bill_number))
        .where(*conds).group_by(Sale.store_id, day)
    ).all()
    out: dict[tuple, dict] = defaultdict(lambda: {"rates": {}, "modes": {}, "bills": 0, "first": None, "last": None})
    for sid, d, rate, taxable, tax in rates:
        out[(sid, d)]["rates"][Decimal(rate)] = (Decimal(taxable or 0), Decimal(tax or 0))
    for sid, d, method, amount in modes:
        out[(sid, d)]["modes"][method] = Decimal(amount or 0)
    for sid, d, count, first, last in bills:
        out[(sid, d)].update(bills=count, first=first, last=last)
    return sorted(out.items(), key=lambda kv: (kv[0][1], kv[0][0]))


def _return_days(store_id: int | None, start: datetime, end: datetime):
    day = db.func.date(db.func.timezone(IST_ZONE, SaleReturn.created_at)).label("day")
    conds = [SaleReturn.created_at >= start, SaleReturn.created_at < end]
    if store_id is not None:
        conds.append(SaleReturn.store_id == store_id)
    rates = db.session.execute(
        select(SaleReturn.store_id, day, SaleReturnItem.tax_rate,
               db.func.sum(SaleReturnItem.line_total - SaleReturnItem.discount_amount),
               db.func.sum(SaleReturnItem.tax_amount))
        .join(SaleReturn, SaleReturn.id == SaleReturnItem.return_id).where(*conds)
        .group_by(SaleReturn.store_id, day, SaleReturnItem.tax_rate)
    ).all()
    modes = db.session.execute(
        select(SaleReturn.store_id, day, SaleReturn.refund_method, db.func.sum(SaleReturn.refund_amount),
               db.func.count(SaleReturn.id))
        .where(*conds).group_by(SaleReturn.store_id, day, SaleReturn.refund_method)
    ).all()
    out: dict[tuple, dict] = defaultdict(lambda: {"rates": {}, "modes": {}, "count": 0})
    for sid, d, rate, taxable, tax in rates:
        out[(sid, d)]["rates"][Decimal(rate)] = (Decimal(taxable or 0), Decimal(tax or 0))
    for sid, d, method, amount, count in modes:
        out[(sid, d)]["modes"][method] = Decimal(amount or 0)
        out[(sid, d)]["count"] += count
    return sorted(out.items(), key=lambda kv: (kv[0][1], kv[0][0]))


def _invoice_rates(inv: SupplierInvoice) -> dict[Decimal, list[Decimal]] | None:
    """GST rate → [taxable, tax] of the goods accepted on the invoice's GRNs (the same maths as the bill)."""
    if not inv.grn_links:
        return None
    rates: dict[Decimal, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])
    for link in inv.grn_links:
        for item in link.goods_receipt.receipt_items:
            poi = item.purchase_order_item
            qty = item.qty_accepted if item.qty_accepted is not None else item.qty_received
            gross, disc, tax = purchase_service._calc_line(qty, poi.unit_price, poi.discount_percent, poi.tax_rate)
            rates[Decimal(poi.tax_rate)][0] += gross - disc
            rates[Decimal(poi.tax_rate)][1] += tax
    return rates


def _invoice_store(inv: SupplierInvoice) -> int | None:
    return inv.store_id or (inv.purchase_order.store_id if inv.purchase_order else None)


def _invoices(store_id: int | None, date_from: date, date_to: date) -> list[SupplierInvoice]:
    rows = db.session.scalars(
        select(SupplierInvoice)
        .where(SupplierInvoice.invoice_date >= date_from, SupplierInvoice.invoice_date <= date_to)
        .where(SupplierInvoice.payment_status != SupplierInvoiceStatus.CANCELLED)
        .order_by(SupplierInvoice.invoice_date, SupplierInvoice.id)
    ).all()
    return [i for i in rows if store_id is None or _invoice_store(i) == store_id]


def _payments(store_id: int | None, date_from: date, date_to: date) -> list[SupplierPayment]:
    q = (
        select(SupplierPayment)
        .where(SupplierPayment.payment_date >= date_from, SupplierPayment.payment_date <= date_to)
        .where(SupplierPayment.is_voided.is_(False))
        .order_by(SupplierPayment.payment_date, SupplierPayment.id)
    )
    if store_id is not None:
        q = q.where(SupplierPayment.store_id == store_id)
    return list(db.session.scalars(q).all())


def _return_parts(ret: SupplierReturn) -> tuple[Decimal, Decimal, Decimal]:
    """(rate, taxable, tax) of goods sent back, at the rate on the GRN they came in on."""
    gri = db.session.scalar(
        select(GoodsReceiptItem).where(
            GoodsReceiptItem.goods_receipt_id == ret.goods_receipt_id, GoodsReceiptItem.product_id == ret.product_id
        )
    )
    if gri is None:
        raise ValueError(f"GRN item not found for supplier return {ret.return_number}")
    poi = gri.purchase_order_item
    gross, disc, tax = purchase_service._calc_line(ret.qty, poi.unit_price, poi.discount_percent, poi.tax_rate)
    return Decimal(poi.tax_rate), gross - disc, tax


def build_vouchers(store_id: int | None, date_from: date, date_to: date) -> tuple[list[Voucher], list[str]]:
    led = get_ledgers()
    stores = _stores()
    start, end = _range(date_from, date_to)
    vouchers: list[Voucher] = []
    warnings: list[str] = []

    def store_name(sid):
        return stores[sid].name if sid in stores else f"store {sid}"

    for (sid, day), d in _sales_days(store_id, start, end):
        lines = _Lines()
        for method, amount in d["modes"].items():
            lines.dr(_mode_ledger(method, led), amount)
        for rate, (taxable, tax) in sorted(d["rates"].items()):
            lines.cr(_name(led.sales, rate), taxable)
            _gst_lines(lines, "cr", rate, tax, interstate=False, cgst=led.output_cgst, sgst=led.output_sgst, igst=None)
        stamp = day.strftime("%Y%m%d")
        what = f"Sales {day} ({store_name(sid)})"
        bills = f"{d['bills']} bill(s)" + (f", {d['first']} to {d['last']}" if d["first"] else "")
        vouchers.append(Voucher(
            guid=f"literetail-sales-{sid}-{stamp}", voucher_type="sales", number=f"POS-{sid}-{stamp}", date=day,
            store_id=sid, party=_mode_ledger(PaymentMethod.CASH, led),
            narration=f"Counter sales, {store_name(sid)}: {bills}", lines=lines.finish(led.round_off, what, warnings),
        ))

    for (sid, day), d in _return_days(store_id, start, end):
        lines = _Lines()
        for rate, (taxable, tax) in sorted(d["rates"].items()):
            lines.dr(_name(led.sales_return, rate), taxable)
            _gst_lines(lines, "dr", rate, tax, interstate=False, cgst=led.output_cgst, sgst=led.output_sgst, igst=None)
        for method, amount in d["modes"].items():
            lines.cr(_mode_ledger(method, led), amount)
        stamp = day.strftime("%Y%m%d")
        vouchers.append(Voucher(
            guid=f"literetail-salesreturn-{sid}-{stamp}", voucher_type="credit_note", number=f"POSRET-{sid}-{stamp}",
            date=day, store_id=sid, party=_mode_ledger(PaymentMethod.CASH, led),
            narration=f"Goods returned at the counter, {store_name(sid)}: {d['count']} return(s)",
            lines=lines.finish(led.round_off, f"Sales returns {day} ({store_name(sid)})", warnings),
        ))

    for txn in _udhari_repayments(store_id, start, end):
        customer = txn.customer
        who = customer.name or customer.mobile
        amount = -Decimal(str(txn.amount))
        lines = _Lines()
        lines.dr(_mode_ledger(txn.payment_method or "cash", led), amount)
        lines.cr(led.udhari, amount)
        vouchers.append(Voucher(
            guid=f"literetail-receipt-{txn.id}", voucher_type="receipt", number=f"UDH-{txn.id}",
            date=txn.created_at.astimezone(IST).date(), store_id=txn.store_id, party=led.udhari,
            reference=txn.reference,
            narration=f"Udhari paid back by {who} ({customer.mobile}) by {txn.payment_method or 'cash'}"
                      + (f" ({txn.reference})" if txn.reference else ""),
            lines=lines.finish(led.round_off, f"Udhari receipt UDH-{txn.id}", warnings),
        ))

    for inv in _invoices(store_id, date_from, date_to):
        supplier = inv.supplier
        what = f"Supplier bill {inv.invoice_number} ({supplier.company_name})"
        rates = _invoice_rates(inv)
        if rates is None:
            warnings.append(f"{what}: not linked to any goods receipt, so the GST rates are unknown. Enter it in Tally by hand.")
            continue
        sid = _invoice_store(inv)
        interstate = _interstate(stores.get(sid), supplier)
        lines = _Lines()
        for rate, (taxable, tax) in sorted(rates.items()):
            lines.dr(_name(led.purchase, rate), taxable)
            _gst_lines(lines, "dr", rate, tax, interstate=interstate,
                       cgst=led.input_cgst, sgst=led.input_sgst, igst=led.input_igst)
        lines.dr(led.freight, inv.other_charges or 0)
        lines.cr(supplier.company_name, inv.payable_amount)
        received = sum((t + x for t, x in rates.values()), ZERO) + Decimal(str(inv.other_charges or 0))
        if Decimal(str(inv.payable_amount)) < received - Decimal("0.05"):
            warnings.append(
                f"{what}: payable ₹{inv.payable_amount} is less than the goods received (₹{round_money(received)}); "
                f"the difference is put to {led.round_off}."
            )
            lines.cr(led.round_off, received - Decimal(str(inv.payable_amount)))
        vouchers.append(Voucher(
            guid=f"literetail-purchase-{inv.id}", voucher_type="purchase", number=f"PUR-{inv.id}", date=inv.invoice_date,
            store_id=sid, party=supplier.company_name, party_gstin=supplier.gstin, reference=inv.invoice_number,
            narration=f"Bill {inv.invoice_number} from {supplier.company_name}"
                      + (f" (GRN {', '.join(g.goods_receipt.receipt_number for g in inv.grn_links)})" if inv.grn_links else "")
                      + (", inter-state (IGST)" if interstate else ""),
            lines=lines.finish(led.round_off, what, warnings),
        ))

    for pay in _payments(store_id, date_from, date_to):
        supplier = pay.supplier
        if pay.payment_type in (SupplierPaymentType.PAYMENT, SupplierPaymentType.ADVANCE):
            ledger = led.cash if pay.payment_method == SupplierPaymentMethod.CASH else led.bank
            lines = _Lines()
            lines.dr(supplier.company_name, pay.amount)
            lines.cr(ledger, pay.amount)
            kind = "Advance" if pay.payment_type == SupplierPaymentType.ADVANCE else "Payment"
            bills = ", ".join(a.invoice.invoice_number for a in pay.allocations if a.invoice)
            vouchers.append(Voucher(
                guid=f"literetail-payment-{pay.id}", voucher_type="payment", number=f"PAY-{pay.id}",
                date=pay.payment_date, store_id=pay.store_id, party=supplier.company_name, party_gstin=supplier.gstin,
                reference=pay.reference_number,
                narration=f"{kind} to {supplier.company_name} by {pay.payment_method.value.replace('_', ' ')}"
                          + (f" ({pay.reference_number})" if pay.reference_number else "")
                          + (f" against bill {bills}" if bills else ""),
                lines=lines.finish(led.round_off, f"Payment PAY-{pay.id}", warnings),
            ))
            continue
        ret = db.session.scalar(select(SupplierReturn).where(SupplierReturn.debit_note_id == pay.id))
        if pay.payment_type != SupplierPaymentType.DEBIT_NOTE or ret is None:
            warnings.append(
                f"{pay.payment_type.value.replace('_', ' ').title()} PAY-{pay.id} ({supplier.company_name}, ₹{pay.amount}) "
                f"is not linked to returned goods. Enter it in Tally by hand."
            )
            continue
        try:
            rate, taxable, tax = _return_parts(ret)
        except ValueError as e:
            warnings.append(f"Debit note for supplier return {ret.return_number} ({supplier.company_name}): {e}. Enter it in Tally by hand.")
            continue
        interstate = _interstate(stores.get(ret.store_id), supplier)
        lines = _Lines()
        lines.dr(supplier.company_name, pay.amount)
        lines.cr(_name(led.purchase_return, rate), taxable)
        _gst_lines(lines, "cr", rate, tax, interstate=interstate,
                   cgst=led.input_cgst, sgst=led.input_sgst, igst=led.input_igst)
        vouchers.append(Voucher(
            guid=f"literetail-debitnote-{ret.id}", voucher_type="debit_note", number=ret.return_number,
            date=pay.payment_date, store_id=ret.store_id, party=supplier.company_name, party_gstin=supplier.gstin,
            reference=ret.goods_receipt.receipt_number if ret.goods_receipt else None,
            narration=f"Goods sent back to {supplier.company_name}: {ret.qty} × "
                      f"{ret.product.name if ret.product else 'item'}: {ret.reason}",
            lines=lines.finish(led.round_off, f"Debit note {ret.return_number}", warnings),
        ))

    order = {"sales": 0, "credit_note": 1, "receipt": 2, "purchase": 3, "debit_note": 4, "payment": 5}
    vouchers.sort(key=lambda v: (v.date, order[v.voucher_type], v.number))
    return vouchers, warnings


def day_book(store_id: int | None, date_from: date, date_to: date) -> DayBookOut:
    vouchers, warnings = build_vouchers(store_id, date_from, date_to)
    counts: dict[str, int] = defaultdict(int)
    for v in vouchers:
        counts[v.voucher_type] += 1
    return DayBookOut(
        date_from=date_from, date_to=date_to, store_id=store_id, warnings=warnings, counts=dict(counts),
        vouchers=[VoucherOut(**v.model_dump(), total_amount=v.total) for v in vouchers],
    )


# ── GST: output (sales) against input (purchases) ────────────────────────────

def gst_summary(store_id: int | None, date_from: date, date_to: date) -> GstSummaryOut:
    stores = _stores()
    start, end = _range(date_from, date_to)
    warnings: list[str] = []
    out: dict[Decimal, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])  # rate → [taxable, tax]
    for _key, d in _sales_days(store_id, start, end):
        for rate, (taxable, tax) in d["rates"].items():
            out[rate][0] += taxable
            out[rate][1] += tax
    for _key, d in _return_days(store_id, start, end):
        for rate, (taxable, tax) in d["rates"].items():
            out[rate][0] -= taxable
            out[rate][1] -= tax

    inp: dict[Decimal, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO, ZERO])  # rate → [taxable, intra, igst]
    for inv in _invoices(store_id, date_from, date_to):
        rates = _invoice_rates(inv)
        if rates is None:
            warnings.append(f"Supplier bill {inv.invoice_number} ({inv.supplier.company_name}) has no goods receipt: "
                            f"its input GST is not included.")
            continue
        interstate = _interstate(stores.get(_invoice_store(inv)), inv.supplier)
        for rate, (taxable, tax) in rates.items():
            inp[rate][0] += taxable
            inp[rate][2 if interstate else 1] += tax
    for pay in _payments(store_id, date_from, date_to):
        if pay.payment_type != SupplierPaymentType.DEBIT_NOTE:
            continue
        ret = db.session.scalar(select(SupplierReturn).where(SupplierReturn.debit_note_id == pay.id))
        if ret is None:
            continue
        try:
            rate, taxable, tax = _return_parts(ret)
        except ValueError as e:
            warnings.append(f"Error processing supplier return {ret.return_number}: {e}")
            continue
        interstate = _interstate(stores.get(ret.store_id), pay.supplier)
        inp[rate][0] -= taxable
        inp[rate][2 if interstate else 1] -= tax

    def row(rate, taxable, intra, igst) -> GstHeadRow:
        c, s = pricing_service.split_gst(intra)
        return GstHeadRow(tax_rate=rate, taxable=round_money(taxable), cgst=c, sgst=s, igst=round_money(igst))

    def total(rows: list[GstHeadRow]) -> GstHeadRow:
        return GstHeadRow(tax_rate=ZERO, taxable=sum((r.taxable for r in rows), ZERO), cgst=sum((r.cgst for r in rows), ZERO),
                          sgst=sum((r.sgst for r in rows), ZERO), igst=sum((r.igst for r in rows), ZERO))

    output = [row(rate, t, x, ZERO) for rate, (t, x) in sorted(out.items())]
    input_ = [row(rate, t, x, i) for rate, (t, x, i) in sorted(inp.items())]
    o, i = total(output), total(input_)
    # GST law: IGST credit is used first against IGST, then CGST, then SGST. Shown simply per head here.
    net_cgst, net_sgst, net_igst = o.cgst - i.cgst, o.sgst - i.sgst, o.igst - i.igst
    return GstSummaryOut(
        date_from=date_from, date_to=date_to, store_id=store_id, output=output, input=input_,
        output_total=o, input_total=i, net_cgst=net_cgst, net_sgst=net_sgst, net_igst=net_igst,
        net_payable=net_cgst + net_sgst + net_igst, warnings=warnings,
    )
