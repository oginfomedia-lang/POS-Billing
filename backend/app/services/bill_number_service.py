"""Builds bill numbers like ST01-C03-20261005-0042 from bill_sequences."""
from __future__ import annotations

from datetime import date

from app.repositories.bill_sequence_repository import BillSequenceRepository
from app.utils.dates import business_date


def format_bill_number(store_id: int, counter_code: str, on: date, number: int) -> str:
    return f"ST{store_id:02d}-{counter_code}-{on:%Y%m%d}-{number:04d}"


def next_bill_number(store_id: int, counter_code: str) -> str:
    """Must run inside the caller's transaction: the sequence row stays locked until commit."""
    number = BillSequenceRepository().next_number(store_id)
    return format_bill_number(store_id, counter_code, business_date(), number)
