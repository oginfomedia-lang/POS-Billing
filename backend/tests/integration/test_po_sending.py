"""Sending a PO to the supplier: automatic email on place, PDF, WhatsApp text, mark as sent."""
from datetime import date
from urllib.parse import unquote

import pytest

from app.errors.exceptions import AppError
from app.extensions import db
from app.models.enums import PaymentTerms
from app.models.purchase import PurchaseOrder
from app.models.supplier import Supplier
from app.services import email_gateway
from tests.factories import make_product

pytestmark = pytest.mark.integration


@pytest.fixture
def emails(monkeypatch):
    """Every email the app sends, instead of the (mock) gateway."""
    sent = []
    monkeypatch.setattr(
        email_gateway, "send",
        lambda to, subject, body, sender_name=None, attachment=None: sent.append(
            {"to": to, "subject": subject, "body": body, "attachment": attachment}
        ),
    )
    return sent


def _supplier(email="orders@sharma.in", phone="98220 12345", **extra):
    s = Supplier(supplier_code=f"SUP-{len(email or '')}{len(phone or '')}", company_name="Sharma Traders",
                 email=email, phone=phone, payment_terms=PaymentTerms.NET_30, **extra)
    db.session.add(s)
    db.session.commit()
    return s


def _po(client, headers, store, supplier, place=True, **extra):
    product = make_product(store, name="Tata Salt 1kg", price="28.00")
    po = client.post("/api/v1/purchases", json={
        "supplier_id": supplier.id, "store_id": store.id, "purchase_date": str(date.today()),
        "items": [{"product_id": product.id, "ordered_qty": "50", "unit_price": "22.00", "tax_rate": "5"}],
        **extra,
    }, headers=headers).get_json()
    if place:
        resp = client.post(f"/api/v1/purchases/{po['id']}/place", headers=headers)
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()
    return po


def test_placing_emails_the_po_with_pdf(client, admin_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier())
    assert po["status"] == "ordered"
    assert po["email_status"] == "sent" and po["email_to"] == "orders@sharma.in"
    assert po["sent_via"] == "email" and po["sent_at"] and po["sent_by_name"]

    assert len(emails) == 1
    mail = emails[0]
    assert mail["to"] == "orders@sharma.in" and po["po_number"] in mail["subject"]
    filename, pdf = mail["attachment"]
    assert filename == f"{po['po_number']}.pdf" and pdf.startswith(b"%PDF")


def test_email_failure_is_recorded_and_order_stays_placed(client, admin_headers, store, monkeypatch):
    def refuse(*a, **k):
        raise AppError("The mail server refused the username or password.")
    monkeypatch.setattr(email_gateway, "send", refuse)

    po = _po(client, admin_headers, store, _supplier())
    assert po["status"] == "ordered"
    assert po["email_status"] == "failed" and "refused" in po["email_error"]
    assert po["sent_at"] is None  # not sent: the screen asks staff to send it another way

    # Retry once the password is fixed.
    monkeypatch.setattr(email_gateway, "send", lambda *a, **k: None)
    again = client.post(f"/api/v1/purchases/{po['id']}/email", headers=admin_headers)
    assert again.status_code == 200, again.get_json()
    assert again.get_json()["email_status"] == "sent" and again.get_json()["email_error"] is None


def test_email_cut_off_by_a_restart_offers_retry(client, admin_headers, store, emails):
    """The background send was killed (server restart) before it saved its result: the PO must not show
    "Sending…" for ever with the Send button greyed out."""
    from datetime import datetime, timedelta, timezone

    po = _po(client, admin_headers, store, _supplier())
    row = db.session.get(PurchaseOrder, po["id"])
    row.email_status = "sending"  # what auto_email() leaves behind if the thread dies
    db.session.commit()

    fresh = client.get(f"/api/v1/purchases/{po['id']}", headers=admin_headers).get_json()
    assert fresh["email_status"] == "sending"  # just started: still sending

    db.session.execute(  # three minutes later, nothing has changed
        db.update(PurchaseOrder).where(PurchaseOrder.id == po["id"])
        .values(updated_at=datetime.now(timezone.utc) - timedelta(minutes=3))
    )
    db.session.commit()
    stuck = client.get(f"/api/v1/purchases/{po['id']}", headers=admin_headers).get_json()
    assert stuck["email_status"] == "failed" and "Retry" in stuck["email_error"]

    again = client.post(f"/api/v1/purchases/{po['id']}/email", headers=admin_headers)
    assert again.status_code == 200 and again.get_json()["email_status"] == "sent"


def test_no_email_without_address_or_setup(client, admin_headers, store, emails, monkeypatch):
    po = _po(client, admin_headers, store, _supplier(email=None))
    assert po["email_status"] is None and emails == []
    resp = client.post(f"/api/v1/purchases/{po['id']}/email", headers=admin_headers)
    assert resp.status_code == 400 and "no email address" in resp.get_json()["error"]["message"]

    monkeypatch.setattr(email_gateway, "is_configured", lambda: False)
    po = _po(client, admin_headers, store, _supplier(email="b@c.in", phone="9822000000"))
    assert po["email_status"] is None and emails == []
    resp = client.post(f"/api/v1/purchases/{po['id']}/email", headers=admin_headers)
    assert resp.status_code == 400 and "not set up" in resp.get_json()["error"]["message"]


def test_draft_is_not_emailed_or_marked(client, admin_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier(), place=False)
    assert emails == []
    assert client.post(f"/api/v1/purchases/{po['id']}/email", headers=admin_headers).status_code == 400
    resp = client.post(f"/api/v1/purchases/{po['id']}/mark-sent", json={"via": "phone"}, headers=admin_headers)
    assert resp.status_code == 400


def test_pdf_download(client, admin_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier(), notes="Deliver before 10 am",
             internal_remarks="Negotiate 2% more next time")
    resp = client.get(f"/api/v1/purchases/{po['id']}/pdf", headers=admin_headers)
    assert resp.status_code == 200 and resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF")
    assert po["po_number"] in resp.headers["Content-Disposition"]


def test_supplier_document_never_shows_internal_remarks(client, admin_headers, store, emails):
    from app.services import po_pdf, po_sending_service

    po = _po(client, admin_headers, store, _supplier(), notes="Deliver before 10 am",
             internal_remarks="Negotiate 2% more next time")
    row = db.session.get(PurchaseOrder, po["id"])
    doc = po_pdf.document(row)
    assert doc.notes == "Deliver before 10 am"
    assert "Negotiate" not in repr(doc)
    assert "Negotiate" not in po_sending_service.order_text(row) and "Negotiate" not in emails[0]["body"]


def test_supplier_message_and_whatsapp_link(client, admin_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier(phone="+91 98220-12345"))
    msg = client.get(f"/api/v1/purchases/{po['id']}/supplier-message", headers=admin_headers).get_json()
    assert msg["supplier_mobile"] == "9822012345"
    assert msg["whatsapp_url"].startswith("https://wa.me/919822012345?text=")
    assert unquote(msg["whatsapp_url"].split("text=", 1)[1]) == msg["text"]
    assert po["po_number"] in msg["text"] and "1. Tata Salt 1kg — 50" in msg["text"]
    assert msg["supplier_email"] == "orders@sharma.in" and msg["email_configured"] is True


def test_landline_supplier_gets_no_whatsapp_link(client, admin_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier(phone="020 2612 3456", alt_phone=None))
    msg = client.get(f"/api/v1/purchases/{po['id']}/supplier-message", headers=admin_headers).get_json()
    assert msg["whatsapp_url"] is None and msg["supplier_mobile"] is None


def test_alt_phone_is_used_when_phone_is_a_landline(client, admin_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier(phone="020 2612 3456", alt_phone="9765432109"))
    msg = client.get(f"/api/v1/purchases/{po['id']}/supplier-message", headers=admin_headers).get_json()
    assert msg["supplier_mobile"] == "9765432109"


def test_mark_sent(client, admin_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier(email=None))
    assert po["sent_at"] is None
    resp = client.post(f"/api/v1/purchases/{po['id']}/mark-sent", json={"via": "whatsapp"}, headers=admin_headers)
    assert resp.status_code == 200, resp.get_json()
    out = resp.get_json()
    assert out["sent_via"] == "whatsapp" and out["sent_at"] and out["sent_by_name"]

    bad = client.post(f"/api/v1/purchases/{po['id']}/mark-sent", json={"via": "pigeon"}, headers=admin_headers)
    assert bad.status_code in (400, 422)


def test_first_send_is_never_overwritten(client, admin_headers, store, emails):
    # Emailed on place: that is the record. Marking it as WhatsApp later is refused, not swapped in.
    po = _po(client, admin_headers, store, _supplier())
    assert po["sent_via"] == "email"
    again = client.post(f"/api/v1/purchases/{po['id']}/mark-sent", json={"via": "whatsapp"}, headers=admin_headers)
    assert again.status_code == 409 and "already recorded as sent" in again.get_json()["error"]["message"]
    assert client.get(f"/api/v1/purchases/{po['id']}", headers=admin_headers).get_json()["sent_via"] == "email"


def test_email_after_whatsapp_keeps_the_whatsapp_record(client, admin_headers, store, emails, monkeypatch):
    monkeypatch.setattr(email_gateway, "is_configured", lambda: False)  # not emailed on place
    po = _po(client, admin_headers, store, _supplier())
    client.post(f"/api/v1/purchases/{po['id']}/mark-sent", json={"via": "whatsapp"}, headers=admin_headers)
    monkeypatch.setattr(email_gateway, "is_configured", lambda: True)
    out = client.post(f"/api/v1/purchases/{po['id']}/email", headers=admin_headers).get_json()
    assert out["email_status"] == "sent" and out["sent_via"] == "whatsapp"  # resending is fine, record unchanged


def test_email_is_not_a_manual_choice(client, admin_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier(email=None))
    resp = client.post(f"/api/v1/purchases/{po['id']}/mark-sent", json={"via": "email"}, headers=admin_headers)
    assert resp.status_code in (400, 422)


def test_cashier_cannot_send(client, admin_headers, cashier_headers, store, emails):
    po = _po(client, admin_headers, store, _supplier(email=None))
    assert client.get(f"/api/v1/purchases/{po['id']}/pdf", headers=cashier_headers).status_code == 403
    resp = client.post(f"/api/v1/purchases/{po['id']}/mark-sent", json={"via": "phone"}, headers=cashier_headers)
    assert resp.status_code == 403
