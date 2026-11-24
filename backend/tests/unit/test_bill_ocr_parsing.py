"""Bill reading without Tesseract: numbers, dates, GSTINs and the table logic on hand-made word boxes."""
from datetime import date
from decimal import Decimal

from app.ocr import Page, Word
from app.ocr import header_parser, normalize, table_parser


# ── normalize ─────────────────────────────────────────────────────────────────

def test_numbers_indian_format_and_ocr_mixups():
    assert normalize.to_decimal("1,24,500.00") == Decimal("124500.00")
    assert normalize.to_decimal("24.50/-") == Decimal("24.50")
    assert normalize.to_decimal("1O") == Decimal("10")
    assert normalize.to_decimal("₹ 99") == Decimal("99")
    assert normalize.to_decimal("10 PCS") == Decimal("10")
    assert normalize.to_decimal("24,50") == Decimal("24.50")
    assert normalize.to_decimal("SALT") is None
    assert normalize.to_decimal("") is None
    assert normalize.to_decimal("120.00 600.00") is None  # two cells read as one: never 12000600.00
    assert normalize.to_decimal("1 24 500.00") == Decimal("124500.00")  # a number OCR split with spaces


def test_rate_and_amount_in_one_column_are_split():
    text = {"name": "TOOR DAL", "qty": "5", "rate": "120.00 600.00"}
    table_parser._split_merged(text, "rate", "amount")
    assert (text["rate"], text["amount"]) == ("120.00", "600.00")
    kept = {"rate": "120.00 600.00", "amount": "600.00"}
    table_parser._split_merged(kept, "rate", "amount")
    assert (kept["rate"], kept["amount"]) == ("120.00", "600.00")  # the amount column already had it


def test_qty_with_free():
    assert normalize.parse_qty("10+1") == (Decimal("10"), Decimal("1"))
    assert normalize.parse_qty("12") == (Decimal("12"), None)


def test_dates_and_expiry():
    assert normalize.parse_date("15/11/2026") == date(2026, 11, 15)
    assert normalize.parse_date("15-Nov-26") == date(2026, 11, 15)
    assert normalize.parse_date("31/02/2026") is None
    assert normalize.parse_expiry("10/27") == date(2027, 10, 31)
    assert normalize.parse_expiry("FEB-28") == date(2028, 2, 29)


def test_hsn():
    assert normalize.clean_hsn("2501") == "2501"
    assert normalize.clean_hsn("25O1") == "2501"
    assert normalize.clean_hsn("12") is None


def test_taxable_value_with_discount_and_gst():
    d = Decimal
    assert normalize.taxable_value(d(10), d("24.50"), d("245.00"), None, None) == d("245.00")
    assert normalize.taxable_value(d(10), d(100), d(980), d(2), None) == d(980)          # 2 % discount
    assert normalize.taxable_value(d(10), d(100), d(1050), None, d(5)) == d(1000)        # amount incl. 5 % GST
    assert normalize.taxable_value(d(10), d(100), d(1500), None, d(5)) is None           # misread


# ── header ────────────────────────────────────────────────────────────────────

def test_gstin_checksum_and_ocr_fix():
    assert header_parser.gstin_checksum_ok("27AAPFU0939F1ZV")
    assert not header_parser.gstin_checksum_ok("27AAPFU0939F1ZW")
    # O read for 0 and 2 read for Z: put right by place
    assert header_parser.find_gstins(["GSTIN: 27AAPFUO939F12V"]) == ["27AAPFU0939F1ZV"]


def test_header_fields():
    lines = [
        "SHREE TRADERS",
        "GSTIN: 27AAPFU0939F1ZV",
        "Invoice No. : GT/2311  Date: 15/11/2026",
        "Sr Description Qty Rate Amount",
        "1 TATA SALT 1KG 10 24.50 245.00",
        "Sub Total 245.00",
        "CGST @ 2.5% 6.13",
        "SGST @ 2.5% 6.13",
        "Round Off -0.26",
        "Grand Total 257.00",
    ]
    h = header_parser.parse(lines)
    assert h.gstins == ["27AAPFU0939F1ZV"]
    assert h.invoice_number == "GT/2311"
    assert h.invoice_date == date(2026, 11, 15)
    assert h.taxable_total == Decimal("245.00")
    assert h.cgst == Decimal("6.13")
    assert h.grand_total == Decimal("257.00")


def test_invoice_number_label_variants():
    assert header_parser.parse(["Invoice Number: A-77"]).invoice_number == "A-77"
    assert header_parser.parse(["Bill No 1234"]).invoice_number == "1234"


# ── table ─────────────────────────────────────────────────────────────────────

def _row(y, *cells):
    """cells = (x, text); every word 10 high, 8 wide per letter."""
    return [Word(text, x, y, x + 8 * len(text), y + 10, 90) for x, text in cells]


def _bill_page():
    words = (
        _row(20, (10, "Invoice"), (80, "No:"), (120, "A-1"))
        + _row(60, (10, "Sr"), (30, "No"), (60, "Item"), (100, "Name"), (300, "HSN"), (380, "Qty"),
               (440, "Rate"), (500, "GST%"), (560, "Amount"))
        + _row(80, (10, "1"), (60, "TATA"), (100, "SALT"), (140, "1KG"), (300, "2501"), (380, "10"),
               (440, "24.50"), (500, "0"), (560, "245.00"))
        # a long name: "OIL" is past halfway to the HSN header, but still part of the name
        + _row(100, (10, "2"), (60, "FORTUNE"), (130, "SOYABEAN"), (210, "OIL"), (300, "1507"), (380, "5+1"),
               (440, "150.00"), (500, "5"), (560, "787.50"))
        + _row(115, (60, "1L"))  # name went on to a second line
        + _row(140, (60, "Total"), (380, "16"), (560, "1032.50"))
        + _row(160, (60, "Thank"), (110, "you"))
    )
    return Page(width=700, height=300, words=words)


def test_table_rows_columns_wrap_and_end():
    lines, layout = table_parser.parse_page(_bill_page(), 1)
    assert [l.description for l in lines] == ["TATA SALT 1KG", "FORTUNE SOYABEAN OIL 1L"]
    salt, oil = lines
    assert (salt.hsn, salt.qty, salt.rate, salt.gst, salt.amount) == ("2501", 10, Decimal("24.50"), 0, Decimal("245.00"))
    assert (oil.hsn, oil.qty, oil.free_qty, oil.amount) == ("1507", 5, 1, Decimal("787.50"))
    fields = [c["field"] for c in layout]
    assert fields == ["_skip", "name", "hsn", "qty", "rate", "gst", "amount"]


def test_speck_in_header_and_serial_in_name():
    """Real OCR of a photo: a "_" speck between "Sr" and "Description" glued them into one column, so the serial
    numbers ended up in the item names."""
    words = (
        _row(60, (10, "Sr"), (30, "_"), (45, "Description"), (300, "HSN"), (380, "Qty"), (440, "Rate"), (560, "Amount"))
        + _row(80, (10, "1"), (45, "TATA"), (85, "SALT"), (300, "2501"), (380, "10"), (440, "24.50"), (560, "245.00"))
        + _row(100, (10, "2"), (45, "7UP"), (80, "2L"), (300, "2202"), (380, "6"), (440, "80.00"), (560, "480.00"))
    )
    lines, layout = table_parser.parse_page(Page(width=700, height=300, words=words), 1)
    assert [c["field"] for c in layout][:2] == ["_skip", "name"]
    assert [l.description for l in lines] == ["TATA SALT", "7UP 2L"]
    # Sr. No. read into the name column anyway (no header column for it): taken off when it is the line's number
    words = [w for w in words if w.text not in ("Sr", "_")]
    lines, _ = table_parser.parse_page(Page(width=700, height=300, words=words), 1)
    assert [l.description for l in lines] == ["TATA SALT", "7UP 2L"]


def test_template_used_when_header_missing():
    _, layout = table_parser.parse_page(_bill_page(), 1)
    page = _bill_page()
    page.words = [w for w in page.words if not (59 <= w.y0 <= 61)]  # header row unreadable
    assert table_parser.parse_page(page, 1)[0] == []                 # no header, no template: nothing
    lines, new_layout = table_parser.parse_page(page, 1, template=layout)
    assert new_layout is None
    assert [l.description for l in lines] == ["TATA SALT 1KG", "FORTUNE SOYABEAN OIL 1L"]

# ── rate and discount for the form (bill_ocr_service._rate_and_discount) ──────

def test_bill_rate_and_discount_percent_kept_as_on_the_bill():
    from app.services.bill_ocr_service import _rate_and_discount
    d = Decimal
    # "Disc 2 %": 10 × 100 = 1000, taxable 980 → rate 100, 2 %
    assert _rate_and_discount(d(10), d(100), None, d(2), d(980)) == (d("100.00"), d("2.00"))
    # "Disc ₹25" on 1000 → 2.5 %, exact
    assert _rate_and_discount(d(10), d(100), None, d(25), d(975)) == (d("100.00"), d("2.50"))
    # "Disc ₹12.35" on 617.50 → 2 % exactly
    assert _rate_and_discount(d(25), d("24.70"), None, d("12.35"), d("605.15")) == (d("24.70"), d("2.00"))
    # no discount
    assert _rate_and_discount(d(10), d("24.50"), None, None, d("245.00")) == (d("24.50"), d("0"))


def test_bill_discount_taken_into_rate_when_no_exact_percent():
    from app.services.bill_ocr_service import _rate_and_discount
    d = Decimal
    # "Disc ₹7" on 3 × 99.99 = 299.97 → 2.3336 %: no 2-decimal % gives 292.97, so the rate carries it
    rate, pct = _rate_and_discount(d(3), d("99.99"), None, d(7), d("292.97"))
    assert pct == 0 and rate == d("97.66")
    # 10 + 1 free at ₹100 → 11 at ₹90.91
    assert _rate_and_discount(d(10), d(100), d(1), None, d(1000)) == (d("90.91"), d("0"))


# ── a real distributor layout: two-line header, scheme ₹ + cash %, taxable column ──

def _two_line_header_page():
    """Like a real bill: "Billed / Qty", "Sch. / Amt.", "Taxable / Amount" headers on two lines."""
    words = (
        _row(40, (30, "Item"), (240, "HSN"), (300, "MRP"), (345, "Billed"), (410, "Rate"), (470, "Amt"),
             (520, "Sch."), (575, "Dis"), (620, "Taxable"), (700, "GST"), (745, "CGST"), (800, "SGST"), (855, "Total"))
        + _row(52, (30, "Description"), (250, "No"), (355, "Qty"), (520, "Amt."), (620, "Amount"), (745, "Amt"),
               (800, "Amt"))
        + _row(70, (30, "Wild"), (65, "Stone"), (110, "Deo"), (240, "33072000"), (300, "225"), (355, "12"),
               (410, "165.81"), (470, "1,989.72"), (520, "331.62"), (580, "1"), (620, "1,641.52"), (705, "18"),
               (745, "147.74"), (800, "147.74"), (850, "1,937.00"))
        + _row(90, (30, "TOTAL"), (75, "Items"), (355, "12"), (850, "1,937.00"))
    )
    return Page(width=950, height=300, words=words)


def test_two_line_header_scheme_and_taxable_columns():
    lines, layout = table_parser.parse_page(_two_line_header_page(), 1)
    assert [c["field"] for c in layout] == ["name", "hsn", "mrp", "qty", "rate", "_skip", "scheme", "discount",
                                            "taxable", "gst", "_skip", "_skip", "amount"]
    (deo,) = lines
    assert (deo.description, deo.qty, deo.rate, deo.free_qty) == ("Wild Stone Deo", 12, Decimal("165.81"), None)
    assert (deo.scheme, deo.discount, deo.taxable, deo.amount) == (Decimal("331.62"), 1, Decimal("1641.52"), Decimal("1937.00"))


def test_scheme_and_cash_discount_become_one_exact_percent():
    from app.services.bill_matching_service import Match
    from app.services.bill_ocr_service import _line_out

    (deo,) = table_parser.parse_page(_two_line_header_page(), 1)[0]
    out = _line_out(deo, Match("not_found"))
    # 12 × 165.81 = 1989.72, 17.50 % off = 348.20 → 1641.52, exactly the bill's taxable amount
    assert (out.qty, out.unit_price, out.discount_percent, out.tax_rate) == (12, 165.81, 17.5, 18)
    assert out.problems == ["discounts_combined"]


def test_footer_labels_on_one_line_and_round_up():
    h = header_parser.parse([
        "Taxable CGST SGST/UTGST Total Round Up (-)0.11",  # a table header: no CGST amount on it
        "Amount In Words: Two Thousand One Hundred Eighty Three Only. Invoice Total 2,183.00",
    ])
    assert (h.cgst, h.sgst, h.round_off, h.grand_total) == (None, None, Decimal("-0.11"), Decimal("2183.00"))


def test_gstin_with_wrong_check_digit_kept_apart():
    h = header_parser.parse(["GSTIN 27AAAPG7873Q1ZE Food L. No. 21526088014921"])
    assert h.gstins == [] and h.unverified_gstins == ["27AAAPG7873Q1ZE"]


def test_noise_with_an_impossible_state_code_is_not_a_gstin():
    # Read off a scanned bill: state 72 does not exist.
    h = header_parser.parse(["GSTIN: 72OIBZZ2522Z5Z9"])
    assert h.gstins == [] and h.unverified_gstins == []


# ── a misread GSTIN still finds the saved supplier ───────────────────────────

SAVED = ["27AAPFU0939F1ZV", "24AAACR5055K1Z3", "29ABCDE1234F1Z5"]


def test_closest_gstin_despite_ocr_mistakes():
    assert header_parser.closest_gstin(["GSTIN : 27AAPFU0939F1ZV"], SAVED) == "27AAPFU0939F1ZV"
    assert header_parser.closest_gstin(["GSTIN 27AAPFUO939FIZW"], SAVED) == "27AAPFU0939F1ZV"  # O/0, I/1, last char
    assert header_parser.closest_gstin(["GSTIN 27AAPFU939F1ZV"], SAVED) == "27AAPFU0939F1ZV"  # a character lost
    assert header_parser.closest_gstin(["G.S.T.I.N 27 AAPFU 0939 F1ZV"], SAVED) == "27AAPFU0939F1ZV"  # spaces
    assert header_parser.closest_gstin(["27aapfu0939f1zv"], ["27 aapfu0939f1zv"]) == "27 aapfu0939f1zv"


def test_closest_gstin_when_the_photo_cuts_it_off():
    # A real bill photo: the paper's edge cut "27AA" off, and OCR read 1 as I. The PAN part is still there.
    saved = ["27AAAPG7873Q1ZE", "27AAPFU0939F1ZV"]
    assert header_parser.closest_gstin(["APG7873QIZE shaileshgandhi294@gmail.com GSTIN No PAN No"],
                                       saved) == "27AAAPG7873Q1ZE"
    assert header_parser.closest_gstin(["GSTIN 27AAAPG7873"], saved) == "27AAAPG7873Q1ZE"  # cut on the right
    assert header_parser.closest_gstin(["Q1ZE"], saved) is None  # too little left to be sure


def test_closest_gstin_refuses_when_unsure():
    assert header_parser.closest_gstin(["GSTIN 27XXPFU0999F9ZV"], SAVED) is None  # 4 characters off
    assert header_parser.closest_gstin(["TOTAL 1,234.00 FSSAI 21526088014921"], SAVED) is None
    # Two saved GSTINs just as close: nobody is picked.
    assert header_parser.closest_gstin(["27AAPFU0939F1ZX"], ["27AAPFU0939F1ZV", "27AAPFU0939F1ZW"]) is None
    # The store's own GSTIN is on the bill: a supplier one character away from it is not chosen from it.
    assert header_parser.closest_gstin(["Bill to 27AAPFU0939F1ZV"], ["27AAPFU0939F1ZW"],
                                       exclude=["27AAPFU0939F1ZV"]) is None
    assert header_parser.closest_gstin(["anything"], []) is None


# ── RapidOCR segments → words ─────────────────────────────────────────────────

def test_rapidocr_segment_split_into_words():
    import numpy as np

    from app.ocr.rapid_engine import segment_words

    box = np.array([[100, 50], [270, 50], [270, 80], [100, 80]], dtype=float)
    words = segment_words(box, "Rice 5kg 10 45.00", 0.9)
    assert [w.text for w in words] == ["Rice", "5kg", "10", "45.00"]
    assert all(a.x1 <= b.x0 for a, b in zip(words, words[1:]))
    assert words[0].x0 == 100 and words[-1].x1 == 270 and words[0].conf == 90

    parts = (("Rice", 0.99, [[100, 50], [140, 50], [140, 80], [100, 80]]),
             ("5kg", 0.98, [[150, 50], [180, 50], [180, 80], [150, 80]]))
    words = segment_words(box, "Rice 5kg", 0.9, parts)
    assert [(w.text, w.x0, w.x1) for w in words] == [("Rice", 100, 140), ("5kg", 150, 180)]


def test_invoice_number_when_the_next_column_runs_into_it():
    h = header_parser.parse(["omobiles Gene Agencies Details for Buyer Invoice Dated No: 8436"])
    assert h.invoice_number == "8436"
    h = header_parser.parse(["Invoice No: Original", "Invoice No. GT/2311"])
    assert h.invoice_number == "GT/2311"  # a word is not an invoice number


# ── a phone photo of a real bill: tight header, handwriting on it ─────────────

def _photo_page():
    """MRP, Billed and Rate printed close together (photo); staff wrote shelf codes and prices on the bill."""
    words = (
        _row(40, (30, "Item"), (240, "HSN"), (300, "MRP"), (328, "Billed"), (380, "Rate"), (430, "Amt"),
             (470, "Sch."), (520, "Dis"), (560, "Taxable"), (630, "GST"), (680, "CGST"), (730, "SGST"), (790, "Total"))
        + _row(52, (30, "Description"), (250, "No"), (340, "Qty"), (470, "Amt."), (560, "Amount"), (680, "Amt"),
               (730, "Amt"))
        # handwritten "9" before the printed MRP 10, "S99" after the total
        + _row(70, (30, "Pen"), (60, "Blue"), (100, "R10"), (240, "96081019"), (300, "9"), (312, "10"), (340, "40"),
               (380, "5.08"), (430, "203.20"), (560, "203.20"), (635, "18"), (680, "18.29"), (730, "18.29"),
               (790, "239.78"), (845, "S99"))
        # qty 1 and rate 249.70 read as one word "1249.70"; handwritten "3" before the printed MRP 30
        + _row(90, (30, "Facewash"), (100, "Rs30"), (240, "34013090"), (300, "330"), (348, "1249.70"),
               (430, "249.70"), (525, "1"), (560, "247.20"), (635, "18"), (680, "22.25"), (730, "22.25"),
               (790, "291.70"), (845, "145"))
        + _row(110, (30, "TOTAL"), (75, "Items"), (340, "41"), (790, "531.48"))
    )
    return Page(width=900, height=300, words=words)


def test_photo_with_handwriting_and_a_tight_header():
    lines, layout = table_parser.parse_page(_photo_page(), 1)
    assert [c["field"] for c in layout][:5] == ["name", "hsn", "mrp", "qty", "rate"]  # "Billed / Qty" kept apart
    pen, wash = lines
    assert (pen.mrp, pen.qty, pen.rate, pen.taxable, pen.amount) == (10, 40, Decimal("5.08"), Decimal("203.20"),
                                                                     Decimal("239.78"))
    assert (wash.mrp, wash.qty, wash.rate, wash.taxable, wash.amount) == (30, 1, Decimal("249.70"),
                                                                          Decimal("247.20"), Decimal("291.70"))


def test_handwriting_next_to_printed_amounts_is_ignored():
    from app.ocr.table_parser import _money, _mrp

    assert _money("239.78 S99") == Decimal("239.78")
    assert _money("997.92 8 16.") == Decimal("997.92")
    assert _money("120.00 600.00") is None  # two printed amounts: not guessed
    assert _money("1,641.52") == Decimal("1641.52")
    assert _mrp("N025", "Trimax Refill Blue R25") == 25
    assert _mrp("go 99", "KS Spark Aerosol 120ml Rs99") == 99
    assert _mrp("235", "Berry 100ml") == 235
    assert _mrp("9 10", "Pen Blue") is None  # two numbers and no price in the name: not guessed


def test_ignored_handwriting_does_not_make_a_line_hard_to_read():
    page = _photo_page()
    for w in page.words:
        if w.text in ("S99", "9", "330", "145"):
            w.conf = 20  # handwriting: OCR is unsure of it, and the line doesn't use it
    pen, wash = table_parser.parse_page(page, 1)[0]
    assert pen.confidence == wash.confidence == 90
    next(w for w in page.words if w.text == "239.78").conf = 30  # a printed amount read badly: still flagged
    pen, _ = table_parser.parse_page(page, 1)[0]
    assert pen.confidence == 30


def test_header_read_off_a_tilted_photo():
    h = header_parser.parse([
        "comobiles Genal Agencies Details for Buyer Invoice Dated No: :21-Oct-26 8447",  # two boxes run together
        "Total: 6,887.01 514.60 514.60 1,029.20",  # the GST summary's total: not the bill's
        "Amount In Words: Indian Rupees Six Thousand Nine Hundred Sixteen Only. Involce Total 6,916.00",
    ])
    assert (h.invoice_number, h.grand_total) == ("8447", Decimal("6916.00"))


# ── a tilted photo: each printed line runs down across the page ─────────────────

def test_rows_follow_a_tilted_line():
    # Two item lines 20 px apart; the text drops 1 px every 20 px to the right (about 3°), so after 600 px a
    # line's right end is lower than the next line's left end.
    words = []
    for n, y in enumerate((100, 120)):
        words += [Word(f"w{n}_{i}", x, y + x / 20, x + 40, y + x / 20 + 10, 90) for i, x in enumerate(range(0, 700, 60))]
    rows = table_parser.group_rows(words)
    assert [len(r.words) for r in rows] == [12, 12]
    assert all(w.text.startswith("w0_") for w in rows[0].words)
