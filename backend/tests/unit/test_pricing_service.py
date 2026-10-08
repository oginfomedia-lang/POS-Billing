"""Tests for GST, discount and round-off calculations."""
from decimal import Decimal

from app.models.enums import DiscountType
from app.services.pricing_service import (
    allocate,
    bill_discount,
    bill_totals,
    buy_x_get_y_discount,
    item_discount,
    line_amounts,
    qty_price_discount,
)

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


def test_percentage_cap():
    assert item_discount(DiscountType.PERCENTAGE, "10", D("5000.00"), 1, D("200")) == D("200.00")
    assert bill_discount(DiscountType.PERCENTAGE, "10", D("5000.00"), D("200")) == D("200.00")


def test_buy_x_get_y_is_proportional():
    assert buy_x_get_y_discount(1, 1, D("20.00")) == D("10.00")  # B1G1, 1 unit -> half price
    assert buy_x_get_y_discount(1, 1, D("40.00")) == D("20.00")  # B1G1, 2 units -> 1 free
    assert buy_x_get_y_discount(2, 1, D("60.00")) == D("20.00")  # B2G1, 3 units -> 1 free
    assert buy_x_get_y_discount(2, 1, D("20.00")) == D("6.67")  # B2G1, 1 unit -> a third off


def test_qty_price_bundle_is_gst_inclusive():
    # 3 x 40 = 120 ex-GST; bundle 99 incl. 0% GST -> saves 21 per bundle
    assert qty_price_discount(D("40.00"), D("3"), D("0"), 3, D("99"), D("120.00")) == D("21.00")
    assert qty_price_discount(D("40.00"), D("2"), D("0"), 3, D("99"), D("80.00")) == D("0.00")
    # 18% GST: bundle 118 incl. GST = 100 ex-GST; 3 x 40 = 120 -> saves 20
    assert qty_price_discount(D("40.00"), D("3"), D("18"), 3, D("118"), D("120.00")) == D("20.00")


# ── MRP savings and GST summary ──────────────────────────────────────────────

from types import SimpleNamespace  # noqa: E402

from app.services.pricing_service import gst_summary, line_saving, split_gst  # noqa: E402


def test_split_gst_always_adds_up():
    assert split_gst(D("5.00")) == (D("2.50"), D("2.50"))
    cgst, sgst = split_gst(D("0.05"))
    assert cgst + sgst == D("0.05")


def test_line_saving_against_mrp():
    # MRP 60 incl. GST; we sell at 50 + 5% GST = 52.50 -> saved 7.50
    assert line_saving(D("60"), 1, D("50.00"), D("0"), D("2.50")) == D("7.50")
    # With an offer of 10 off (GST on 40 = 2.00): paid 42.00 -> saved 18.00
    assert line_saving(D("60"), 1, D("50.00"), D("10.00"), D("2.00")) == D("18.00")


def test_line_saving_weighed_item_and_no_mrp():
    # MRP ₹100/kg, 0.5 kg sold at ₹80/kg (40.00) + 5% (2.00) -> MRP 50 - 42 = 8
    assert line_saving(D("100"), D("0.5"), D("40.00"), D("0"), D("2.00")) == D("8.00")
    # No MRP: the saving is just the discount
    assert line_saving(None, 2, D("100.00"), D("15.00"), D("4.25")) == D("15.00")
    # Never negative (price above MRP)
    assert line_saving(D("10"), 1, D("50.00"), D("0"), D("0")) == D("0")


def test_gst_summary_groups_by_rate():
    lines = [
        SimpleNamespace(tax_rate=D("5"), line_total=D("100"), discount_amount=D("10"), tax_amount=D("4.50")),
        SimpleNamespace(tax_rate=D("18"), line_total=D("50"), discount_amount=D("0"), tax_amount=D("9.00")),
        SimpleNamespace(tax_rate=D("5"), line_total=D("20"), discount_amount=D("0"), tax_amount=D("1.00")),
    ]
    rows = gst_summary(lines)
    assert [r["tax_rate"] for r in rows] == [D("5"), D("18")]
    assert rows[0] == {"tax_rate": D("5"), "taxable": D("110.00"), "cgst": D("2.75"), "sgst": D("2.75"), "tax": D("5.50")}
    assert rows[1]["cgst"] + rows[1]["sgst"] == D("9.00")
