"""Tally import file (XML) from the accounting vouchers.

In Tally: Gateway of Tally → Import → Transactions (TallyPrime) / Import of Data → Vouchers (Tally.ERP 9).
- Debit lines: ISDEEMEDPOSITIVE Yes and a negative AMOUNT; credit lines: No and a positive AMOUNT (Tally's way).
- Each voucher has a REMOTEID made from the POS record (the same sale day, bill or payment always gets the same
  one), so Tally can tell a voucher it has already imported.
- A separate ledgers file (Cash, Sales @5%, Input CGST @2.5%, each supplier ...) under Tally's standard groups,
  to import once, before the vouchers, into a company that doesn't have them yet.
"""
from __future__ import annotations

from decimal import Decimal
from xml.sax.saxutils import escape, quoteattr

from app.schemas.accounting_schemas import TallyLedgers, Voucher

VCHTYPE = {
    "sales": "Sales",
    "credit_note": "Credit Note",
    "receipt": "Receipt",
    "purchase": "Purchase",
    "payment": "Payment",
    "debit_note": "Debit Note",
}


def _amount(value: Decimal) -> str:
    return f"{value:.2f}"


def _voucher_xml(v: Voucher) -> str:
    vtype = VCHTYPE[v.voucher_type]
    parts = [
        f"<VOUCHER REMOTEID={quoteattr(v.guid)} VCHTYPE={quoteattr(vtype)} ACTION=\"Create\" "
        f"OBJVIEW=\"Accounting Voucher View\">",
        f"<DATE>{v.date.strftime('%Y%m%d')}</DATE>",
        f"<EFFECTIVEDATE>{v.date.strftime('%Y%m%d')}</EFFECTIVEDATE>",
        f"<GUID>{escape(v.guid)}</GUID>",
        f"<VOUCHERTYPENAME>{escape(vtype)}</VOUCHERTYPENAME>",
        f"<VOUCHERNUMBER>{escape(v.number)}</VOUCHERNUMBER>",
        f"<PARTYLEDGERNAME>{escape(v.party)}</PARTYLEDGERNAME>",
        f"<PERSISTEDVIEW>Accounting Voucher View</PERSISTEDVIEW>",
        f"<NARRATION>{escape(v.narration)}</NARRATION>",
    ]
    if v.reference:
        parts.append(f"<REFERENCE>{escape(v.reference)}</REFERENCE>")
    if v.party_gstin:
        parts.append(f"<PARTYGSTIN>{escape(v.party_gstin)}</PARTYGSTIN>")
    for line in v.lines:
        debit = line.debit > 0
        amount = -line.debit if debit else line.credit
        parts.append(
            "<ALLLEDGERENTRIES.LIST>"
            f"<LEDGERNAME>{escape(line.ledger)}</LEDGERNAME>"
            f"<ISDEEMEDPOSITIVE>{'Yes' if debit else 'No'}</ISDEEMEDPOSITIVE>"
            f"<ISPARTYLEDGER>{'Yes' if line.ledger == v.party else 'No'}</ISPARTYLEDGER>"
            f"<AMOUNT>{_amount(amount)}</AMOUNT>"
            "</ALLLEDGERENTRIES.LIST>"
        )
    parts.append("</VOUCHER>")
    return "".join(parts)


def ledger_groups(vouchers: list[Voucher], led: TallyLedgers) -> dict[str, tuple[str, str | None]]:
    """Every ledger the vouchers use → (Tally group, GST duty head or None)."""
    fixed = {
        led.cash: ("Cash-in-Hand", None),
        led.upi: ("Bank Accounts", None),
        led.card: ("Bank Accounts", None),
        led.bank: ("Bank Accounts", None),
        led.udhari: ("Sundry Debtors", None),  # what customers owe on khata
        led.freight: ("Direct Expenses", None),
        led.round_off: ("Indirect Expenses", None),
    }
    prefixes = [  # template → group; matched on the part before {rate} / {half}
        (led.sales, "Sales Accounts", None), (led.sales_return, "Sales Accounts", None),
        (led.purchase, "Purchase Accounts", None), (led.purchase_return, "Purchase Accounts", None),
        (led.output_cgst, "Duties & Taxes", "Central Tax"), (led.output_sgst, "Duties & Taxes", "State Tax"),
        (led.input_cgst, "Duties & Taxes", "Central Tax"), (led.input_sgst, "Duties & Taxes", "State Tax"),
        (led.input_igst, "Duties & Taxes", "Integrated Tax"),
    ]
    out: dict[str, tuple[str, str | None]] = {}
    for v in vouchers:
        for line in v.lines:
            name = line.ledger
            if name in out:
                continue
            if name in fixed:
                out[name] = fixed[name]
            elif v.voucher_type in ("purchase", "payment", "debit_note") and name == v.party:
                out[name] = ("Sundry Creditors", None)
            else:
                for template, group, head in prefixes:
                    head_part = template.split("{")[0]
                    if name == template or (head_part and name.startswith(head_part)):
                        out[name] = (group, head)
                        break
                else:
                    out[name] = ("Suspense A/c", None)
    return out


def _ledger_xml(name: str, group: str, head: str | None, gstin: str | None) -> str:
    # ACTION="Create or Alter" lets Tally update an existing ledger instead of silently
    # skipping it, so re-importing the masters file (e.g. after adding new suppliers) is safe.
    parts = [
        f"<LEDGER NAME={quoteattr(name)} ACTION=\"Create or Alter\">",
        f"<NAME.LIST><NAME>{escape(name)}</NAME></NAME.LIST>",
        f"<PARENT>{escape(group)}</PARENT>",
    ]
    if head:
        parts.append(f"<TAXTYPE>GST</TAXTYPE><GSTDUTYHEAD>{escape(head)}</GSTDUTYHEAD>")
    if group == "Sundry Creditors":
        parts.append("<ISBILLWISEON>No</ISBILLWISEON>")
        if gstin:
            parts.append(f"<PARTYGSTIN>{escape(gstin)}</PARTYGSTIN>")
    parts.append("</LEDGER>")
    return "".join(parts)


def _envelope(report: str, messages: list[str]) -> str:
    body = "".join(f"<TALLYMESSAGE xmlns:UDF=\"TallyUDF\">{m}</TALLYMESSAGE>" for m in messages)
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<ENVELOPE>"
        "<HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>"
        "<BODY><IMPORTDATA>"
        f"<REQUESTDESC><REPORTNAME>{report}</REPORTNAME></REQUESTDESC>"
        f"<REQUESTDATA>{body}</REQUESTDATA>"
        "</IMPORTDATA></BODY>"
        "</ENVELOPE>\n"
    )


def vouchers_xml(vouchers: list[Voucher]) -> str:
    return _envelope("Vouchers", [_voucher_xml(v) for v in vouchers])


def ledgers_xml(vouchers: list[Voucher], led: TallyLedgers) -> str:
    """The ledgers the vouchers use, to import once (before the vouchers) into a company that lacks them."""
    gstins = {v.party: v.party_gstin for v in vouchers if v.party_gstin}
    return _envelope("All Masters", [
        _ledger_xml(name, group, head, gstins.get(name))
        for name, (group, head) in ledger_groups(vouchers, led).items()
    ])
