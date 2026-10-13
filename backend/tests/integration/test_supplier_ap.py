"""Supplier payments go against the supplier's invoice, never the PO, and never exceed the goods received."""
import io
import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.supplier import Supplier
from app.models.supplier_invoice import SupplierInvoice
from tests.factories import make_product

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.4 test invoice"


@pytest.fixture
def supplier(app):
    s = Supplier(supplier_code="SUP-AAA111", company_name="Sharma Traders", payment_terms=PaymentTerms.NET_30)
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture
def other_supplier(app):
    s = Supplier(supplier_code="SUP-BBB222", company_name="Patil Agencies")
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture(autouse=True)
def upload_dir(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def _po(client, headers, supplier, store, product, qty=100, price="10", tax="5"):
    """PO placed with the supplier (ordered), ready to receive goods."""
    resp = client.post("/api/v1/purchases", json={
        "supplier_id": supplier.id, "store_id": store.id, "purchase_date": str(date.today()),
        "items": [{"product_id": product.id, "ordered_qty": qty, "unit_price": price, "tax_rate": tax}],
    }, headers=headers)
    assert resp.status_code == 201, resp.get_json()
    po = resp.get_json()
    assert client.post(f"/api/v1/purchases/{po['id']}/place", headers=headers).status_code == 200
    return po


def _receive(client, headers, po, qty, accepted=None):
    item = {"purchase_order_item_id": po["items"][0]["id"], "qty_received": qty}
    if accepted is not None:
        item.update(qty_accepted=accepted, qty_rejected=qty - accepted)
    resp = client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [item]}, headers=headers)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _invoice(client, headers, supplier, grn_ids, total, number="INV-1", reason=None, file=True, other="0"):
    data = {
        "supplier_id": supplier.id, "invoice_number": number, "invoice_date": str(date.today()),
        "grand_total": str(total), "other_charges": other, "grn_ids": grn_ids,
        **({"difference_reason": reason} if reason else {}),
    }
    form = {"data": json.dumps(data)}
    if file:
        form["file"] = (io.BytesIO(PDF), "bill.pdf", "application/pdf")
    return client.post("/api/v1/supplier-invoices", data=form, headers=headers, content_type="multipart/form-data")


def _pay(client, headers, supplier, allocations, amount=None):
    amount = amount if amount is not None else sum(Decimal(str(a)) for _, a in allocations)
    return client.post("/api/v1/supplier-payments", json={
        "supplier_id": supplier.id, "payment_date": str(date.today()), "amount": str(amount),
        "payment_method": "upi", "reference_number": "UTR123",
        "allocations": [{"invoice_id": i, "allocated_amount": str(a)} for i, a in allocations],
    }, headers=headers)


@pytest.fixture
def received(client, admin_headers, supplier, store):
    """PO for 100 × ₹10 + 5% GST; only 80 arrived → goods received worth ₹840."""
    po = _po(client, admin_headers, supplier, store, make_product(store, name="Rice 1kg"))
    grn = _receive(client, admin_headers, po, 80)
    return po, grn


def test_invoice_matching_goods_received(client, admin_headers, supplier, received):
    po, grn = received
    grns = client.get(f"/api/v1/suppliers/{supplier.id}/grns?uninvoiced=1", headers=admin_headers).get_json()
    assert [(g["id"], g["value"], g["invoice_id"]) for g in grns] == [(grn["id"], "840.00", None)]
    preview = client.get(f"/api/v1/supplier-invoices/preview-grns?supplier_id={supplier.id}&grn_ids={grn['id']}",
                         headers=admin_headers).get_json()
    assert preview["received_value"] == "840.00" and preview["po_number"] == po["po_number"]

    resp = _invoice(client, admin_headers, supplier, [grn["id"]], "840.40")  # 40 paise round-off is fine
    assert resp.status_code == 201, resp.get_json()
    inv = resp.get_json()
    assert inv["verification_status"] == "verified" and inv["payable_amount"] == "840.00"
    assert inv["purchase_order_id"] == po["id"] and inv["grn_numbers"] == [grn["receipt_number"]]
    assert inv["document_id"] is not None  # the bill's file is attached
    assert inv["due_date"] == str(date.today() + timedelta(days=30))  # supplier is net 30

    doc = client.get(f"/api/v1/documents/{inv['document_id']}/download", headers=admin_headers)
    assert doc.status_code == 200 and doc.data == PDF
    assert client.get(f"/api/v1/suppliers/{supplier.id}/grns?uninvoiced=1", headers=admin_headers).get_json() == []


def test_invoice_for_more_than_received_needs_reason_and_pays_only_received(client, admin_headers, supplier, received):
    po, grn = received
    resp = _invoice(client, admin_headers, supplier, [grn["id"]], "1050")  # billed for all 100
    assert resp.status_code == 400
    assert resp.get_json()["error"]["details"]["received_value"] == "840.00"

    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "1050", reason="Billed for 100, only 80 came").get_json()
    assert inv["verification_status"] == "disputed" and inv["difference"] == "210.00"
    assert (inv["payable_amount"], inv["outstanding"]) == ("840.00", "840.00")

    too_much = _pay(client, admin_headers, supplier, [(inv["id"], "1050")])
    assert too_much.status_code == 400 and "840" in too_much.get_json()["error"]["message"]


def test_other_charges_are_payable(client, admin_headers, supplier, received):
    _, grn = received
    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "890", other="50").get_json()  # 840 goods + 50 freight
    assert inv["verification_status"] == "verified" and inv["payable_amount"] == "890.00"


def test_rejected_goods_are_not_paid_for(client, admin_headers, supplier, store):
    po = _po(client, admin_headers, supplier, store, make_product(store, name="Oil 1L"))
    grn = _receive(client, admin_headers, po, 50, accepted=40)  # 10 damaged and rejected
    assert client.get(f"/api/v1/suppliers/{supplier.id}/grns", headers=admin_headers).get_json()[0]["value"] == "420.00"


def test_invoice_rules(client, admin_headers, supplier, other_supplier, store, received):
    po, grn = received
    assert _invoice(client, admin_headers, supplier, [grn["id"]], "840", file=False).status_code == 400  # file required
    assert _invoice(client, admin_headers, supplier, [], "840").status_code == 400  # GRNs required
    assert _invoice(client, admin_headers, other_supplier, [grn["id"]], "840").status_code == 400  # not their goods

    assert _invoice(client, admin_headers, supplier, [grn["id"]], "840").status_code == 201
    again = _invoice(client, admin_headers, supplier, [grn["id"]], "840", number="INV-2")
    assert again.status_code == 409 and "INV-1" in again.get_json()["error"]["message"]  # billed already
    assert _invoice(client, admin_headers, supplier, [grn["id"]], "840").status_code == 409  # same number

    po2 = _po(client, admin_headers, supplier, store, make_product(store, name="Dal 1kg"))
    grn2 = _receive(client, admin_headers, po2, 10)
    grn3 = _receive(client, admin_headers, _po(client, admin_headers, supplier, store, make_product(store, name="Tea")), 5)
    two_pos = _invoice(client, admin_headers, supplier, [grn2["id"], grn3["id"]], "157.50", number="INV-3")
    assert two_pos.status_code == 400 and "one purchase order" in two_pos.get_json()["error"]["message"]


def test_payments_against_invoices(client, admin_headers, supplier, received):
    _, grn = received
    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "840").get_json()

    first = _pay(client, admin_headers, supplier, [(inv["id"], "500")])
    assert first.status_code == 201, first.get_json()
    now = client.get(f"/api/v1/supplier-invoices/{inv['id']}", headers=admin_headers).get_json()
    assert (now["payment_status"], now["amount_paid"], now["outstanding"]) == ("partially_paid", "500.00", "340.00")

    assert _pay(client, admin_headers, supplier, [(inv["id"], "400")]).status_code == 400  # more than left
    assert _pay(client, admin_headers, supplier, [(inv["id"], "300")], amount="340").status_code == 400  # must add up
    assert _pay(client, admin_headers, supplier, [], amount="100").status_code == 400  # must be against an invoice

    last = _pay(client, admin_headers, supplier, [(inv["id"], "340")]).get_json()
    assert client.get(f"/api/v1/supplier-invoices/{inv['id']}", headers=admin_headers).get_json()["payment_status"] == "paid"

    assert client.post(f"/api/v1/supplier-payments/{last['id']}/void", headers=admin_headers).status_code == 200
    now = client.get(f"/api/v1/supplier-invoices/{inv['id']}", headers=admin_headers).get_json()
    assert (now["payment_status"], now["outstanding"]) == ("partially_paid", "340.00")


def test_one_payment_for_two_invoices(client, admin_headers, supplier, store, received):
    po, grn1 = received
    grn2 = _receive(client, admin_headers, po, 20)  # the rest arrived later: ₹210
    inv1 = _invoice(client, admin_headers, supplier, [grn1["id"]], "840").get_json()
    inv2 = _invoice(client, admin_headers, supplier, [grn2["id"]], "210", number="INV-2").get_json()
    paid = _pay(client, admin_headers, supplier, [(inv1["id"], "840"), (inv2["id"], "100")])
    assert paid.status_code == 201
    assert [a["invoice_number"] for a in paid.get_json()["allocations"]] == ["INV-1", "INV-2"]

    summary = client.get(f"/api/v1/purchases/{po['id']}/payment-summary", headers=admin_headers).get_json()
    assert summary["invoice_count"] == 2 and summary["received_value"] == "1050.00"
    assert (summary["payable_amount"], summary["total_paid"], summary["outstanding"]) == ("1050.00", "940.00", "110.00")
    assert summary["payment_status"] == "partially_paid"
    history = client.get(f"/api/v1/purchases/{po['id']}/payment-history", headers=admin_headers).get_json()
    assert [e["invoice_number"] for e in history["entries"]] == ["INV-1", "INV-2"]


def test_po_has_no_payment_button_any_more(client, admin_headers, received):
    po, _ = received
    resp = client.post(f"/api/v1/purchases/{po['id']}/quick-payment", json={"amount": "100"}, headers=admin_headers)
    assert resp.status_code in (404, 405)
    listed = client.get("/api/v1/purchases", headers=admin_headers).get_json()["items"][0]
    assert listed["payment_status"] == "not_invoiced" and listed["not_invoiced_value"] == "840.00"


def test_supplier_summary_and_ledger(client, admin_headers, supplier, store, received):
    po, grn = received
    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "1050", reason="Billed 100").get_json()
    _pay(client, admin_headers, supplier, [(inv["id"], "500")])
    _receive(client, admin_headers, po, 20)  # not invoiced yet

    s = client.get(f"/api/v1/suppliers/{supplier.id}/summary", headers=admin_headers).get_json()
    assert s["total_po_value"] == 1050.0
    assert s["total_received_value"] == 1050.0 and s["not_invoiced_value"] == 210.0
    assert (s["total_invoiced"], s["total_payable"], s["total_paid"]) == (1050.0, 840.0, 500.0)
    assert s["outstanding_balance"] == 340.0 and s["disputed_count"] == 1

    ledger = client.get(f"/api/v1/suppliers/{supplier.id}/ledger", headers=admin_headers).get_json()
    assert [(e["debit"], e["credit"]) for e in ledger] == [(840.0, 0.0), (0.0, 500.0)]
    assert ledger[-1]["balance"] == 340.0 and "payable ₹840" in ledger[0]["description"]


def test_old_invoice_without_grns_can_still_be_paid(client, admin_headers, supplier):
    old = SupplierInvoice(
        supplier_id=supplier.id, invoice_number="INV-PO-OLD", invoice_date=date.today(),
        grand_total=Decimal("500"), payable_amount=Decimal("500"),
    )
    db.session.add(old)
    db.session.commit()
    inv = client.get(f"/api/v1/supplier-invoices/{old.id}", headers=admin_headers).get_json()
    assert inv["is_legacy"] is True and inv["outstanding"] == "500.00"
    assert _pay(client, admin_headers, supplier, [(old.id, "500")]).status_code == 201


def test_edit_invoice_recomputes_and_protects_payments(client, admin_headers, supplier, received):
    _, grn = received
    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "1050", reason="Billed 100").get_json()
    _pay(client, admin_headers, supplier, [(inv["id"], "800")])
    fixed = client.put(f"/api/v1/supplier-invoices/{inv['id']}", json={"grand_total": "840"}, headers=admin_headers)
    assert fixed.status_code == 200 and fixed.get_json()["verification_status"] == "verified"
    lower = client.put(f"/api/v1/supplier-invoices/{inv['id']}", json={"grand_total": "700", "difference_reason": "credit"},
                       headers=admin_headers)
    assert lower.status_code == 400  # ₹800 already paid


# ── Rejected goods, advances, cancel ──────────────────────────────────────────

def _stock(product_id):
    from app.models.inventory import Inventory
    return db.session.scalar(db.select(Inventory.qty_on_hand).where(Inventory.product_id == product_id))


def test_only_accepted_goods_go_into_stock(client, admin_headers, supplier, store):
    oil = make_product(store, name="Oil 1L", stock=0)
    po = _po(client, admin_headers, supplier, store, oil, qty=50)
    item = po["items"][0]["id"]

    bad = client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [
        {"purchase_order_item_id": item, "qty_received": 50, "qty_accepted": 45, "qty_rejected": 10},
    ]}, headers=admin_headers)
    assert bad.status_code == 422 and "must equal" in bad.get_json()["error"]["message"]

    ok = client.post(f"/api/v1/purchases/{po['id']}/receipts", json={"items": [
        {"purchase_order_item_id": item, "qty_received": 50, "qty_rejected": 10},  # accepted = 40
    ]}, headers=admin_headers)
    assert ok.status_code == 201, ok.get_json()
    assert ok.get_json()["receipt_items"][0]["qty_accepted"] == "40.000"
    assert _stock(oil.id) == Decimal("40")

    # The 10 rejected are still owed: the PO is partly received and takes the replacement.
    detail = client.get(f"/api/v1/purchases/{po['id']}", headers=admin_headers).get_json()
    assert detail["status"] == "partially_received" and detail["items"][0]["received_qty"] == "40.000"
    _receive(client, admin_headers, detail, 10)
    assert _stock(oil.id) == Decimal("50")
    assert client.get(f"/api/v1/purchases/{po['id']}", headers=admin_headers).get_json()["status"] == "received"


def _advance(client, headers, supplier, amount, allocations=()):
    return client.post("/api/v1/supplier-payments", json={
        "supplier_id": supplier.id, "payment_date": str(date.today()), "amount": str(amount),
        "payment_type": "advance", "payment_method": "bank_transfer",
        "allocations": [{"invoice_id": i, "allocated_amount": str(a)} for i, a in allocations],
    }, headers=headers)


def test_advance_before_the_bill_then_applied(client, admin_headers, supplier, store):
    adv = _advance(client, admin_headers, supplier, 1000)
    assert adv.status_code == 201, adv.get_json()
    adv = adv.get_json()
    assert adv["unallocated_amount"] == "1000.00" and adv["allocations"] == []
    summary = client.get(f"/api/v1/suppliers/{supplier.id}/summary", headers=admin_headers).get_json()
    assert summary["advance_balance"] == 1000.0 and summary["outstanding_balance"] == -1000.0

    po = _po(client, admin_headers, supplier, store, make_product(store, name="Rice 1kg"))
    grn = _receive(client, admin_headers, po, 80)
    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "840").get_json()

    url = f"/api/v1/supplier-payments/{adv['id']}/apply"
    too_much = client.post(url, json={"allocations": [{"invoice_id": inv["id"], "allocated_amount": "900"}]}, headers=admin_headers)
    assert too_much.status_code == 400  # invoice balance is only 840
    applied = client.post(url, json={"allocations": [{"invoice_id": inv["id"], "allocated_amount": "840"}]}, headers=admin_headers)
    assert applied.status_code == 200 and applied.get_json()["unallocated_amount"] == "160.00"
    assert client.get(f"/api/v1/supplier-invoices/{inv['id']}", headers=admin_headers).get_json()["payment_status"] == "paid"

    summary = client.get(f"/api/v1/suppliers/{supplier.id}/summary", headers=admin_headers).get_json()
    assert (summary["total_paid"], summary["advance_balance"], summary["outstanding_balance"]) == (840.0, 160.0, -160.0)
    ledger = client.get(f"/api/v1/suppliers/{supplier.id}/ledger", headers=admin_headers).get_json()
    assert ledger[-1]["balance"] == -160.0

    # Voiding the advance makes the invoice unpaid again.
    client.post(f"/api/v1/supplier-payments/{adv['id']}/void", headers=admin_headers)
    assert client.get(f"/api/v1/supplier-invoices/{inv['id']}", headers=admin_headers).get_json()["outstanding"] == "840.00"
    assert client.get(f"/api/v1/suppliers/{supplier.id}/summary", headers=admin_headers).get_json()["advance_balance"] == 0.0


def test_advance_rules(client, admin_headers, supplier, received):
    _, grn = received
    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "840").get_json()
    assert _advance(client, admin_headers, supplier, 100, [(inv["id"], "200")]).status_code == 400  # more than the advance
    part = _advance(client, admin_headers, supplier, 1000, [(inv["id"], "300")]).get_json()  # part now, rest later
    assert part["unallocated_amount"] == "700.00"
    normal = _pay(client, admin_headers, supplier, [(inv["id"], "100")]).get_json()
    apply_normal = client.post(f"/api/v1/supplier-payments/{normal['id']}/apply",
                               json={"allocations": [{"invoice_id": inv["id"], "allocated_amount": "1"}]}, headers=admin_headers)
    assert apply_normal.status_code == 400  # only advances
    # Topping up the same invoice from the same advance adds to its line.
    again = client.post(f"/api/v1/supplier-payments/{part['id']}/apply",
                        json={"allocations": [{"invoice_id": inv["id"], "allocated_amount": "440"}]}, headers=admin_headers).get_json()
    assert [a["allocated_amount"] for a in again["allocations"]] == ["740.00"] and again["unallocated_amount"] == "260.00"


def test_cancel_invoice_frees_its_grns(client, admin_headers, supplier, received):
    _, grn = received
    wrong = _invoice(client, admin_headers, supplier, [grn["id"]], "840", number="INV-WRONG").get_json()
    url = f"/api/v1/supplier-invoices/{wrong['id']}/cancel"
    assert client.post(url, json={"reason": ""}, headers=admin_headers).status_code == 422  # reason required

    cancelled = client.post(url, json={"reason": "Duplicate bill"}, headers=admin_headers)
    assert cancelled.status_code == 200
    body = cancelled.get_json()
    assert body["payment_status"] == "cancelled" and body["grn_ids"] == [] and "Duplicate bill" in body["notes"]
    assert client.post(url, json={"reason": "again"}, headers=admin_headers).status_code == 400
    assert client.put(f"/api/v1/supplier-invoices/{wrong['id']}", json={"notes": "x"}, headers=admin_headers).status_code == 400
    assert _pay(client, admin_headers, supplier, [(wrong["id"], "100")]).status_code == 400

    right = _invoice(client, admin_headers, supplier, [grn["id"]], "840", number="INV-RIGHT")  # GRN is free again
    assert right.status_code == 201
    s = client.get(f"/api/v1/suppliers/{supplier.id}/summary", headers=admin_headers).get_json()
    assert (s["total_invoiced"], s["total_payable"]) == (840.0, 840.0)  # cancelled one left out


def test_cannot_cancel_a_paid_invoice(client, admin_headers, supplier, received):
    _, grn = received
    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "840").get_json()
    pay = _pay(client, admin_headers, supplier, [(inv["id"], "100")]).get_json()
    url = f"/api/v1/supplier-invoices/{inv['id']}/cancel"
    assert client.post(url, json={"reason": "wrong"}, headers=admin_headers).status_code == 400
    client.post(f"/api/v1/supplier-payments/{pay['id']}/void", headers=admin_headers)
    assert client.post(url, json={"reason": "wrong"}, headers=admin_headers).status_code == 200


def test_edit_invoice_and_replace_bill(client, admin_headers, supplier, received):
    _, grn = received
    inv = _invoice(client, admin_headers, supplier, [grn["id"]], "840").get_json()
    edited = client.put(f"/api/v1/supplier-invoices/{inv['id']}", json={
        "invoice_number": "INV-1A", "due_date": str(date.today()), "notes": "checked",
    }, headers=admin_headers).get_json()
    assert (edited["invoice_number"], edited["notes"], edited["payable_amount"]) == ("INV-1A", "checked", "840.00")

    new_file = client.post("/api/v1/documents/upload", data={
        "file": (io.BytesIO(b"%PDF-1.4 corrected"), "bill2.pdf", "application/pdf"),
        "entity_type": "supplier_invoice", "entity_id": str(inv["id"]),
    }, headers=admin_headers, content_type="multipart/form-data")
    assert new_file.status_code == 201
    now = client.get(f"/api/v1/supplier-invoices/{inv['id']}", headers=admin_headers).get_json()
    assert now["document_id"] == new_file.get_json()["id"]  # the latest bill is shown
