"""Tests for bill number formatting."""
from datetime import date

from app.services.bill_number_service import format_bill_number


def test_format_bill_number():
    assert format_bill_number(1, "C03", date(2026, 10, 5), 42) == "ST01-C03-20261005-0042"


def test_format_bill_number_wide_values():
    assert format_bill_number(123, "C10", date(2026, 1, 9), 12345) == "ST123-C10-20260109-12345"
