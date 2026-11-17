"""The suggested selling price: cost + target profit, + GST, never above MRP, no rounding to a 'nice' number."""
from decimal import Decimal as D

from app.services.price_review_service import margin_percent, price_with_gst, suggest


def test_cost_plus_target_plus_gst():
    s = suggest(D("90"), D("5"), mrp=D("110"), target=D("12"))
    assert s.price == D("100.80")  # before GST: 90 × 1.12
    assert s.price_incl == D("105.84")  # + 5% GST, exact to the paisa
    assert s.margin_percent == D("12.00") and not s.capped


def test_sugar_example_no_rounding():
    s = suggest(D("45"), D("5"), mrp=None, target=D("5"))
    assert (s.price, s.price_incl) == (D("47.25"), D("49.61"))


def test_never_below_the_target_by_a_paisa():
    s = suggest(D("33.3333"), D("0"), mrp=None, target=D("10"))
    assert s.price == D("36.67")  # 36.66663 rounded UP: the profit is never under 10%
    assert s.margin_percent >= D("10")


def test_capped_at_mrp_when_the_target_is_not_possible():
    s = suggest(D("90"), D("5"), mrp=D("100"), target=D("12"))
    assert s.capped
    assert s.price_incl <= D("100")
    assert s.price == D("95.24") and s.price_incl == D("100.00")  # 95.24 + 4.76 GST = exactly the MRP
    assert s.margin_percent == D("5.82")


def test_exactly_at_mrp_is_allowed():
    s = suggest(D("100"), D("0"), mrp=D("110"), target=D("10"))
    assert (s.price, s.capped) == (D("110.00"), False)


def test_gst_rounding_never_pushes_over_mrp():
    for mrp in ("10.00", "99.99", "47.13", "1234.57"):
        for rate in ("5", "12", "18", "28"):
            s = suggest(D("5000"), D(rate), mrp=D(mrp), target=D("10"))  # the MRP is always the limit
            assert s.capped and s.price_incl <= D(mrp)
            assert price_with_gst(s.price + D("0.01"), D(rate)) > D(mrp)  # and it is the most the MRP allows


def test_margin_on_cost():
    assert margin_percent(D("110"), D("100")) == D("10.00")
    assert margin_percent(D("90"), D("100")) == D("-10.00")
    assert margin_percent(D("10"), D("0")) is None
