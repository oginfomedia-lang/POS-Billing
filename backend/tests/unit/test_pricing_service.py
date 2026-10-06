"""Tests for GST, discount and round-off calculations."""
from decimal import Decimal

from app.services.pricing_service import bill_totals, line_amounts


def test_line_amounts():
    assert line_amounts(Decimal("19.99"), 3, Decimal("18")) == (Decimal("59.97"), Decimal("10.79"))


def test_line_amounts_zero_tax():
    assert line_amounts("50", 2, "0") == (Decimal("100.00"), Decimal("0.00"))


def test_bill_totals():
    totals = bill_totals([(Decimal("100.00"), Decimal("5.00")), (Decimal("59.97"), Decimal("10.79"))])
    assert totals == {
        "subtotal": Decimal("159.97"),
        "discount_amount": Decimal("0.00"),
        "tax_amount": Decimal("15.79"),
        "total": Decimal("175.76"),
    }


def test_bill_totals_empty():
    assert bill_totals([])["total"] == Decimal("0.00")
