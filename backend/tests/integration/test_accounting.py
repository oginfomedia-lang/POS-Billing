"""Accounting for Tally: vouchers built from sales, returns, supplier bills, payments and goods sent back; every
voucher balances; GST output against input; the Tally XML file."""
import io
import json
import xml.etree.ElementTree as ET
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.inventory import StockBatch
from app.models.supplier import Supplier
from tests.factories import make_counter, make_product, make_shift, make_user, pay_by_razorpay

pytestmark = pytest.mark.integration

TODAY = str(date.today())


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store), opening_float="500.00")


@pytest.fixture
def manager(store):
    return make_user(role="manager", username="mgr", pin="4321", store=store)


@pytest.fixture
def supplier(app):
    s = Supplier(supplier_code="SUP-AAA111", company_name="Sharma Traders", payment_terms=PaymentTerms.NET_30,
                 gstin="27AAAAA0000A1Z5")
    db.session.add(s)
    db.session.commit()
    return s


def _cart(client, headers, *lines):
    sid = client.post("/api/v1/sales", headers=headers).get_json()["id"]
    for product, qty in lines:
        resp = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
        assert resp.status_code in (200, 201), resp.get_json()
    return sid


def _cash_sale(client, headers, *lines):
    sid = _cart(client, headers, *lines)
    resp = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "10000"}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _receive_and_bill(client, headers, supplier, store, product, qty, price="10", tax="5", number="INV-1"):
    po = client.post("/api/v1/purchases", json={
        "supplier_id": supplier.id, "store_id": store.id, "purchase_date": TODAY,
        "items": [{"product_id": product.id, "ordered_qty": qty, "unit_price": price, "tax_rate": tax}],
    }, headers=headers).get_json()
    assert client.post(f"/api/v1/purchases/{po['id']}/place", headers=headers).status_code == 200
    grn = client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [
        {"purchase_order_item_id": po["items"][0]["id"], "qty_received": qty},
    ]}, headers=headers).get_json()
    total = Decimal(price) * qty * (1 + Decimal(tax) / 100)
    data = {"supplier_id": supplier.id, "invoice_number": number, "invoice_date": TODAY, "grand_total": str(total),
            "other_charges": "0", "grn_ids": [grn["id"]]}
    form = {"data": json.dumps(data), "file": (io.BytesIO(b"%PDF-1.4"), "bill.pdf", "application/pdf")}
    inv = client.post("/api/v1/supplier-invoices", data=form, headers=headers, content_type="multipart/form-data")
    assert inv.status_code == 201, inv.get_json()
    return grn, inv.get_json()


def _daybook(client, headers, **params):
    resp = client.get("/api/v1/accounting/daybook", query_string={"date_from": TODAY, "date_to": TODAY, **params},
                      headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _lines(voucher) -> dict[str, tuple[Decimal, Decimal]]:
    return {ln["ledger"]: (Decimal(ln["debit"]), Decimal(ln["credit"])) for ln in voucher["lines"]}


def _balanced(voucher) -> bool:
    return sum(Decimal(ln["debit"]) for ln in voucher["lines"]) == sum(Decimal(ln["credit"]) for ln in voucher["lines"])


@pytest.fixture(autouse=True)
def upload_dir(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "UPLOAD_DIR", str(tmp_path))


def test_one_sales_voucher_per_day_by_rate_and_payment_mode(client, admin_headers, cashier_headers, store, shift):
    rice = make_product(store, name="Rice", price="100.00", tax_rate="5.00")
    soap = make_product(store, name="Soap", price="50.00", tax_rate="18.00")
    _cash_sale(client, cashier_headers, (rice, 2), (soap, 1))   # 200 + 10 GST, 50 + 9 GST = 269
    sid = _cart(client, cashier_headers, (rice, 1))              # 100 + 5 = 105 by UPI
    assert pay_by_razorpay(client, cashier_headers, sid).get_json()["status"] == "paid"

    book = _daybook(client, admin_headers)
    sales = [v for v in book["vouchers"] if v["voucher_type"] == "sales"]
    assert len(sales) == 1 and book["warnings"] == []
    v = sales[0]
    assert v["party"] == "Cash" and v["number"].startswith(f"POS-{store.id}-") and "2 bill(s)" in v["narration"]
    assert _balanced(v) and Decimal(v["total_amount"]) == Decimal("374.00")
    assert _lines(v) == {
        "Cash": (Decimal("269.00"), Decimal("0")),
        "Bank Account": (Decimal("105.00"), Decimal("0")),
        "Sales @5%": (Decimal("0"), Decimal("300.00")),
        "Output CGST @2.5%": (Decimal("0"), Decimal("7.50")),
        "Output SGST @2.5%": (Decimal("0"), Decimal("7.50")),
        "Sales @18%": (Decimal("0"), Decimal("50.00")),
        "Output CGST @9%": (Decimal("0"), Decimal("4.50")),
        "Output SGST @9%": (Decimal("0"), Decimal("4.50")),
    }


def test_sales_return_is_a_credit_note(client, admin_headers, cashier_headers, store, shift, manager):
    oil = make_product(store, name="Oil", price="100.00", tax_rate="5.00")
    bill = _cash_sale(client, cashier_headers, (oil, 2))
    resp = client.post("/api/v1/returns", json={
        "bill_number": bill["bill_number"], "lines": [{"sale_item_id": bill["items"][0]["id"], "qty": 1}],
        "reason": "Leaking", "approver_username": "mgr", "approver_pin": "4321",
    }, headers=cashier_headers)
    assert resp.status_code == 201, resp.get_json()

    note = next(v for v in _daybook(client, admin_headers)["vouchers"] if v["voucher_type"] == "credit_note")
    assert _balanced(note)
    # Credit note debits the "Sales Return" ledger (not the Sales ledger) to reverse the sale.
    assert _lines(note) == {
        "Sales Return @5%": (Decimal("100.00"), Decimal("0")),
        "Output CGST @2.5%": (Decimal("2.50"), Decimal("0")),
        "Output SGST @2.5%": (Decimal("2.50"), Decimal("0")),
        "Cash": (Decimal("0"), Decimal("105.00")),
    }
    gst = client.get("/api/v1/accounting/gst-summary", query_string={"date_from": TODAY}, headers=admin_headers).get_json()
    assert gst["output"][0]["taxable"] == "100.00" and gst["output_total"]["cgst"] == "2.50"  # 200 sold − 100 back


def test_purchase_payment_and_debit_note(client, admin_headers, store, supplier):
    rice = make_product(store, name="Rice 1kg", stock=0)
    grn, inv = _receive_and_bill(client, admin_headers, supplier, store, rice, 80)  # 800 + 40 GST
    pay = client.post("/api/v1/supplier-payments", json={
        "supplier_id": supplier.id, "store_id": store.id, "payment_date": TODAY, "amount": "500",
        "payment_method": "upi", "reference_number": "UTR123",
        "allocations": [{"invoice_id": inv["id"], "allocated_amount": "500"}],
    }, headers=admin_headers)
    assert pay.status_code == 201, pay.get_json()
    batch = db.session.scalar(db.select(StockBatch).where(StockBatch.source == "grn"))
    back = client.post(f"/api/v1/inventory/batches/{batch.id}/return-to-supplier",
                       json={"qty": "10", "reason": "Expired"}, headers=admin_headers)
    assert back.status_code == 201, back.get_json()

    book = _daybook(client, admin_headers)
    assert book["warnings"] == [] and book["counts"] == {"purchase": 1, "payment": 1, "debit_note": 1}
    by_type = {v["voucher_type"]: v for v in book["vouchers"]}
    assert all(_balanced(v) for v in book["vouchers"])

    purchase = by_type["purchase"]
    assert purchase["party"] == "Sharma Traders" and purchase["reference"] == "INV-1"
    assert _lines(purchase) == {
        "Purchase @5%": (Decimal("800.00"), Decimal("0")),
        "Input CGST @2.5%": (Decimal("20.00"), Decimal("0")),
        "Input SGST @2.5%": (Decimal("20.00"), Decimal("0")),
        "Sharma Traders": (Decimal("0"), Decimal("840.00")),
    }
    assert _lines(by_type["payment"]) == {
        "Sharma Traders": (Decimal("500.00"), Decimal("0")), "Bank Account": (Decimal("0"), Decimal("500.00")),
    }
    assert _lines(by_type["debit_note"]) == {
        "Sharma Traders": (Decimal("105.00"), Decimal("0")),
        "Purchase @5%": (Decimal("0"), Decimal("100.00")),
        "Input CGST @2.5%": (Decimal("0"), Decimal("2.50")),
        "Input SGST @2.5%": (Decimal("0"), Decimal("2.50")),
    }

    gst = client.get("/api/v1/accounting/gst-summary", query_string={"date_from": TODAY}, headers=admin_headers).get_json()
    assert (gst["input_total"]["taxable"], gst["input_total"]["cgst"], gst["input_total"]["igst"]) == ("700.00", "17.50", "0.00")
    assert gst["net_payable"] == "-35.00"  # no sales yet: input credit carried forward


def test_supplier_in_another_state_gives_igst(client, admin_headers, store, supplier):
    store.gstin = "27BBBBB1111B1Z5"   # Maharashtra
    supplier.gstin = "29CCCCC2222C1Z5"  # Karnataka
    db.session.commit()
    _receive_and_bill(client, admin_headers, supplier, store, make_product(store, name="Tea", stock=0), 10, tax="12")
    purchase = _daybook(client, admin_headers)["vouchers"][0]
    assert _lines(purchase) == {
        "Purchase @12%": (Decimal("100.00"), Decimal("0")),
        "Input IGST @12%": (Decimal("12.00"), Decimal("0")),
        "Sharma Traders": (Decimal("0"), Decimal("112.00")),
    }
    gst = client.get("/api/v1/accounting/gst-summary", query_string={"date_from": TODAY}, headers=admin_headers).get_json()
    assert gst["input_total"]["igst"] == "12.00" and gst["input_total"]["cgst"] == "0.00"


def test_ledger_names_follow_the_settings(client, admin_headers, cashier_headers, store, shift):
    names = client.get("/api/v1/accounting/ledgers", headers=admin_headers).get_json()
    names.update(cash="Cash in Hand", sales="GST Sales {rate}%", output_cgst="CGST {half}%", output_sgst="SGST {half}%")
    resp = client.put("/api/v1/accounting/ledgers", json=names, headers=admin_headers)
    assert resp.status_code == 200 and resp.get_json()["cash"] == "Cash in Hand"
    assert client.put("/api/v1/accounting/ledgers", json={**names, "cash": "  "}, headers=admin_headers).status_code == 422

    _cash_sale(client, cashier_headers, (make_product(store, name="Dal", price="100.00", tax_rate="5.00"), 1))
    v = _daybook(client, admin_headers)["vouchers"][0]
    assert set(_lines(v)) == {"Cash in Hand", "GST Sales 5%", "CGST 2.5%", "SGST 2.5%"} and v["party"] == "Cash in Hand"


def test_tally_xml(client, admin_headers, cashier_headers, store, shift, supplier):
    _cash_sale(client, cashier_headers, (make_product(store, name="Rice", price="100.00", tax_rate="5.00"), 1))
    _receive_and_bill(client, admin_headers, supplier, store, make_product(store, name="Sugar & Co", stock=0), 5)

    resp = client.get("/api/v1/accounting/tally-export", query_string={"date_from": TODAY}, headers=admin_headers)
    assert resp.status_code == 200 and "attachment" in resp.headers["Content-Disposition"]
    root = ET.fromstring(resp.data)
    assert root.findtext("BODY/IMPORTDATA/REQUESTDESC/REPORTNAME") == "Vouchers"
    vouchers = root.findall(".//VOUCHER")
    assert [v.get("VCHTYPE") for v in vouchers] == ["Sales", "Purchase"]
    sale = vouchers[0]
    assert sale.get("REMOTEID") == sale.findtext("GUID") and sale.findtext("DATE") == date.today().strftime("%Y%m%d")
    entries = {e.findtext("LEDGERNAME"): (e.findtext("ISDEEMEDPOSITIVE"), Decimal(e.findtext("AMOUNT")))
               for e in sale.findall("ALLLEDGERENTRIES.LIST")}
    assert entries["Cash"] == ("Yes", Decimal("-105.00"))       # debit: negative in Tally
    assert entries["Sales @5%"] == ("No", Decimal("100.00"))    # credit: positive
    assert sum(amount for _, amount in entries.values()) == 0
    assert vouchers[1].findtext("PARTYGSTIN") == "27AAAAA0000A1Z5"

    # Same day exported again: the same voucher ids, so Tally knows them.
    again = ET.fromstring(client.get("/api/v1/accounting/tally-export", query_string={"date_from": TODAY},
                                     headers=admin_headers).data)
    assert [v.get("REMOTEID") for v in again.findall(".//VOUCHER")] == [v.get("REMOTEID") for v in vouchers]

    masters = ET.fromstring(client.get("/api/v1/accounting/tally-export",
                                       query_string={"date_from": TODAY, "what": "ledgers"}, headers=admin_headers).data)
    groups = {led.get("NAME"): led.findtext("PARENT") for led in masters.findall(".//LEDGER")}
    assert groups["Cash"] == "Cash-in-Hand" and groups["Sales @5%"] == "Sales Accounts"
    assert groups["Purchase @5%"] == "Purchase Accounts" and groups["Sharma Traders"] == "Sundry Creditors"
    assert groups["Output CGST @2.5%"] == "Duties & Taxes" and groups["Input SGST @2.5%"] == "Duties & Taxes"
    gst_heads = {led.get("NAME"): led.findtext("GSTDUTYHEAD") for led in masters.findall(".//LEDGER")}
    assert gst_heads["Output CGST @2.5%"] == "Central Tax" and gst_heads["Input SGST @2.5%"] == "State Tax"
    # Ledger masters use ACTION="Create or Alter" so re-importing is always safe.
    actions = {led.get("NAME"): led.get("ACTION") for led in masters.findall(".//LEDGER")}
    assert all(a == "Create or Alter" for a in actions.values())


def test_cashier_cannot_open_the_books(client, cashier_headers):
    assert client.get("/api/v1/accounting/daybook", headers=cashier_headers).status_code == 403


def test_debit_note_without_grn_item_becomes_warning_not_crash(client, admin_headers, store, supplier):
    """If the GRN item for a supplier return is missing (orphaned data), the debit note must not crash
    the day book — it must appear as a human-readable warning instead."""
    from app.models.supplier_return import SupplierReturn

    # A real return of goods (the database allows nothing less), then its product is changed to one the GRN
    # never had: the GRN line the debit note is valued from can no longer be found.
    rice = make_product(store, name="Rice 1kg", stock=0)
    _receive_and_bill(client, admin_headers, supplier, store, rice, 20)
    batch = db.session.scalar(db.select(StockBatch).where(StockBatch.source == "grn"))
    back = client.post(f"/api/v1/inventory/batches/{batch.id}/return-to-supplier",
                       json={"qty": "2", "reason": "Expired"}, headers=admin_headers)
    assert back.status_code == 201, back.get_json()
    ret = db.session.get(SupplierReturn, back.get_json()["id"])
    ret.product_id = make_product(store, name="Dal 1kg", stock=0).id
    db.session.commit()

    book = _daybook(client, admin_headers)
    # Must not crash: the orphaned debit note becomes a warning, not a voucher.
    assert any(ret.return_number in w for w in book["warnings"])
    assert all(v["voucher_type"] != "debit_note" for v in book["vouchers"])
