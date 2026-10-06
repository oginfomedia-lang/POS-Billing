"""Tests for GST, discount and round-off calculations."""
from decimal import Decimal

from app.models.enums import DiscountType
from app.services.pricing_service import allocate, bill_discount, bill_totals, item_discount, line_amounts

D = Decimal


def test_line_amounts():
    assert line_amounts(D("19.99"), 3, D("18")) == (D("59.97"), D("10.79"))


def test_line_amounts_zero_tax():
    assert line_amounts("50", 2, "0") == (D("100.00"), D("0.00"))


def test_line_amounts_tax_is_on_discounted_value():
    # 100 - 10 discount = 90 taxable at 5%
    assert line_amounts("50", 2, "5", D("10")) == (D("100.00"), D("4.50"))


def test_item_discount_percentage_and_fixed_per_unit():
    assert item_discount(DiscountType.PERCENTAGE, "10", D("150.00"), 3) == D("15.00")
    assert item_discount(DiscountType.FIXED, "5", D("150.00"), 3) == D("15.00")


def test_item_discount_never_exceeds_line():
    assert item_discount(DiscountType.FIXED, "80", D("150.00"), 3) == D("150.00")


def test_bill_discount():
    assert bill_discount(DiscountType.PERCENTAGE, "5", D("999.00")) == D("49.95")
    assert bill_discount(DiscountType.FIXED, "50", D("30.00")) == D("30.00")


def test_allocate_is_proportional_and_exact():
    shares = allocate(D("10.00"), [D("100.00"), D("50.00"), D("50.00")])
    assert shares == [D("5.00"), D("2.50"), D("2.50")]
    odd = allocate(D("0.10"), [D("1"), D("1"), D("1")])
    assert sum(odd) == D("0.10")


def test_allocate_nothing():
    assert allocate(D("0"), [D("5")]) == [D("0.00")]
    assert allocate(D("5"), []) == []


def test_bill_totals():
    totals = bill_totals([(D("100.00"), D("10.00"), D("4.50")), (D("59.97"), D("0.00"), D("10.79"))])
    assert totals == {
        "subtotal": D("159.97"),
        "discount_amount": D("10.00"),
        "tax_amount": D("15.29"),
        "total": D("165.26"),
    }


def test_bill_totals_empty():
    assert bill_totals([])["total"] == D("0.00")
