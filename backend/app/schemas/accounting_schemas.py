"""Accounting (Tally) schemas: ledger names, vouchers, GST summary."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# In ledger names, {rate} = the GST rate ("5", "12", "18"); {half} = half of it, for CGST / SGST ("2.5", "6", "9").


class TallyLedgers(BaseModel):
    """The exact ledger names in the shop's Tally company. They must match Tally letter for letter."""

    cash: str = Field("Cash", min_length=1, max_length=100)
    upi: str = Field("Bank Account", min_length=1, max_length=100)
    card: str = Field("Bank Account", min_length=1, max_length=100)
    bank: str = Field("Bank Account", min_length=1, max_length=100)  # supplier payments not made in cash
    udhari: str = Field("Udhari Customers", min_length=1, max_length=100)  # bills sold on khata (Sundry Debtors)
    sales: str = Field("Sales @{rate}%", min_length=1, max_length=100)
    sales_return: str = Field("Sales Return @{rate}%", min_length=1, max_length=100)
    purchase: str = Field("Purchase @{rate}%", min_length=1, max_length=100)
    purchase_return: str = Field("Purchase @{rate}%", min_length=1, max_length=100)
    output_cgst: str = Field("Output CGST @{half}%", min_length=1, max_length=100)
    output_sgst: str = Field("Output SGST @{half}%", min_length=1, max_length=100)
    input_cgst: str = Field("Input CGST @{half}%", min_length=1, max_length=100)
    input_sgst: str = Field("Input SGST @{half}%", min_length=1, max_length=100)
    input_igst: str = Field("Input IGST @{rate}%", min_length=1, max_length=100)
    freight: str = Field("Freight Inward", min_length=1, max_length=100)  # a supplier bill's other charges
    round_off: str = Field("Round Off", min_length=1, max_length=100)

    @field_validator("*", mode="before")
    @classmethod
    def strip(cls, value):
        return value.strip() if isinstance(value, str) else value


VoucherType = Literal["sales", "credit_note", "receipt", "purchase", "payment", "debit_note"]


class VoucherLine(BaseModel):
    ledger: str
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


class Voucher(BaseModel):
    guid: str  # stable id for the same POS record: Tally's REMOTEID
    voucher_type: VoucherType
    number: str
    date: date
    store_id: int | None
    party: str  # Tally's party ledger (Cash for counter sales, the supplier for purchases)
    party_gstin: str | None = None
    reference: str | None = None  # supplier's bill number etc.
    narration: str
    lines: list[VoucherLine]

    @property
    def total(self) -> Decimal:
        return sum((ln.debit for ln in self.lines), Decimal("0"))


class VoucherOut(Voucher):
    total_amount: Decimal = Decimal("0")


class DayBookOut(BaseModel):
    date_from: date
    date_to: date
    store_id: int | None
    vouchers: list[VoucherOut]
    # Records that could not be turned into a voucher (say why, so the accountant enters them by hand)
    warnings: list[str]
    counts: dict[str, int]


class GstHeadRow(BaseModel):
    tax_rate: Decimal
    taxable: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal


class GstSummaryOut(BaseModel):
    date_from: date
    date_to: date
    store_id: int | None
    output: list[GstHeadRow]  # sales − sales returns
    input: list[GstHeadRow]  # purchases − goods sent back
    output_total: GstHeadRow
    input_total: GstHeadRow
    # Output − input per head. Negative = more input credit than tax collected (carried forward).
    net_cgst: Decimal
    net_sgst: Decimal
    net_igst: Decimal
    net_payable: Decimal
    warnings: list[str]
