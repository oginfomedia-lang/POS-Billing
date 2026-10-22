"""Bills priced by the server's own rules, written to frontend/tests/fixtures/pricing-cases.json. The counter's offline
pricing (frontend/src/offline/pricing.ts) must give exactly these results (frontend tests/unit/offlinePricing.test.ts).

When pricing rules change on purpose: run with UPDATE_PRICING_CASES=1 to rewrite the file, then run the frontend tests.
"""
import json
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models.category import Category
from app.models.discount import Discount
from app.models.enums import DiscountScope, DiscountType
from app.services import discount_service, pricing_service

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[3] / "frontend" / "tests" / "fixtures" / "pricing-cases.json"

# Food (101) > Snacks (102) > Chips (103); Drinks (104)
CATEGORIES = {101: None, 102: 101, 103: 102, 104: None}


def _offer(id, name, type, value, scope, **kw):
    return {"id": id, "name": name, "discount_type": type, "value": value, "scope": scope,
            "product_id": kw.get("product_id"), "category_id": kw.get("category_id"),
            "min_bill_amount": kw.get("min_bill_amount"), "max_discount_amount": kw.get("max_discount_amount"),
            "buy_qty": kw.get("buy_qty"), "get_qty": kw.get("get_qty"), "starts_at": None, "ends_at": None}


def _line(product_id, price, qty, tax, category_id=None):
    return {"product_id": product_id, "category_id": category_id, "unit_price": price, "tax_rate": tax, "qty": qty}


CASES = [
    ("no offers, mixed GST", [_line(1, "45.50", "3", "5.00"), _line(2, "99.99", "1", "18.00"), _line(3, "12.00", "2", "0.00")], []),
    ("product % with cap", [_line(1, "250.00", "4", "12.00")],
     [_offer(1, "15% off (max ₹100)", "percentage", "15.00", "product", product_id=1, max_discount_amount="100.00")]),
    ("product fixed per unit", [_line(1, "30.00", "5", "5.00"), _line(2, "10.00", "1", "5.00")],
     [_offer(2, "₹3 off each", "fixed", "3.00", "product", product_id=1)]),
    ("category offer reaches sub-category", [_line(1, "20.00", "3", "12.00", 103), _line(2, "40.00", "1", "12.00", 104)],
     [_offer(3, "Snacks 10%", "percentage", "10.00", "category", category_id=102)]),
    ("buy 2 get 1, full group", [_line(1, "60.00", "3", "5.00")],
     [_offer(4, "Buy 2 Get 1", "buy_x_get_y", "0.00", "product", product_id=1, buy_qty=2, get_qty=1)]),
    ("buy 1 get 1, odd qty", [_line(1, "33.33", "3", "18.00")],
     [_offer(5, "B1G1", "buy_x_get_y", "0.00", "product", product_id=1, buy_qty=1, get_qty=1)]),
    ("3 for 99 incl GST, 7 units", [_line(1, "35.00", "7", "5.00")],
     [_offer(6, "3 for ₹99", "qty_price", "99.00", "product", product_id=1, buy_qty=3)]),
    ("bill % beats item offer", [_line(1, "100.00", "2", "5.00"), _line(2, "150.00", "1", "18.00")],
     [_offer(7, "₹5 off item", "fixed", "5.00", "product", product_id=1),
      _offer(8, "10% on ₹300+", "percentage", "10.00", "bill", min_bill_amount="300.00")]),
    ("bill fixed split with remainder", [_line(1, "10.00", "1", "5.00"), _line(2, "10.00", "1", "5.00"), _line(3, "10.01", "1", "5.00")],
     [_offer(9, "₹10 off bill", "fixed", "10.00", "bill")]),
    ("bill minimum not met (checked with GST)", [_line(1, "95.00", "1", "5.00")],
     [_offer(10, "₹20 off ₹100+", "fixed", "20.00", "bill", min_bill_amount="100.00")]),
    ("bill minimum met only with GST", [_line(1, "96.00", "1", "5.00")],
     [_offer(11, "₹20 off ₹100+", "fixed", "20.00", "bill", min_bill_amount="100.00")]),
    ("loose item by weight", [_line(1, "42.00", "1.235", "0.00"), _line(2, "180.00", "0.375", "5.00")],
     [_offer(12, "8% loose", "percentage", "8.00", "product", product_id=2)]),
    ("tie keeps the first offer", [_line(1, "50.00", "2", "5.00")],
     [_offer(13, "First ₹10", "fixed", "5.00", "product", product_id=1),
      _offer(14, "Second ₹10", "fixed", "10.00", "bill")]),
    ("bill % with cap", [_line(1, "1999.00", "1", "18.00"), _line(2, "1.00", "3", "0.00")],
     [_offer(15, "5% max ₹50", "percentage", "5.00", "bill", max_discount_amount="50.00")]),
]


def _discount(o) -> Discount:
    return Discount(
        id=o["id"], name=o["name"], discount_type=DiscountType(o["discount_type"]), value=Decimal(o["value"]),
        scope=DiscountScope(o["scope"]), product_id=o["product_id"], category_id=o["category_id"],
        min_bill_amount=Decimal(o["min_bill_amount"]) if o["min_bill_amount"] else None,
        max_discount_amount=Decimal(o["max_discount_amount"]) if o["max_discount_amount"] else None,
        buy_qty=o["buy_qty"], get_qty=o["get_qty"],
    )


def _price(lines, offers) -> dict:
    """billing_service._recalculate for a bill without manual discounts or reward points."""
    items = [SimpleNamespace(product_id=ln["product_id"], product=SimpleNamespace(category_id=ln["category_id"]),
                             unit_price=Decimal(ln["unit_price"]), qty=Decimal(ln["qty"]),
                             tax_rate=Decimal(ln["tax_rate"])) for ln in lines]
    for item in items:
        item.line_total = pricing_service.line_amounts(item.unit_price, item.qty, item.tax_rate)[0]
    room = [item.line_total for item in items]
    with_gst = sum((r + pricing_service.line_amounts(i.unit_price, i.qty, i.tax_rate)[1] for i, r in zip(items, room)),
                   pricing_service.ZERO)
    chosen = discount_service.choose_best_offer([_discount(o) for o in offers], items, room, with_gst)
    out_lines, totals_in = [], []
    for item, off in zip(items, chosen.line_amounts):
        on_line = not chosen.is_bill_offer and off > 0
        line_total, tax = pricing_service.line_amounts(item.unit_price, item.qty, item.tax_rate, off)
        out_lines.append({
            "line_total": str(line_total), "offer_id": chosen.offer.discount_id if on_line else None,
            "offer_name": chosen.offer.name if on_line else None,
            "offer_discount": str(off if on_line else pricing_service.ZERO), "discount_amount": str(off),
            "tax_amount": str(tax),
        })
        totals_in.append((line_total, off, tax))
    totals = pricing_service.bill_totals(totals_in)
    return {
        "lines": out_lines,
        "bill_offer_id": chosen.offer.discount_id if chosen.is_bill_offer else None,
        "bill_offer_name": chosen.offer.name if chosen.is_bill_offer else None,
        "bill_offer_discount": str(chosen.offer.amount if chosen.is_bill_offer else pricing_service.ZERO),
        **{k: str(v) for k, v in totals.items()},
    }


def test_pricing_cases_match_the_fixture(app):
    for cid, parent in CATEGORIES.items():
        db.session.add(Category(id=cid, name=f"Category {cid}", parent_id=parent))
    db.session.commit()

    cases = [{"name": name, "lines": lines, "offers": offers, "categories": {str(k): v for k, v in CATEGORIES.items()},
              "expected": _price(lines, offers)} for name, lines, offers in CASES]
    text = json.dumps(cases, ensure_ascii=False, indent=2) + "\n"
    if os.environ.get("UPDATE_PRICING_CASES") == "1" or not FIXTURE.exists():
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(text, encoding="utf-8")
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == cases, (
        "Server pricing changed: run with UPDATE_PRICING_CASES=1, then make frontend src/offline/pricing.ts match."
    )
