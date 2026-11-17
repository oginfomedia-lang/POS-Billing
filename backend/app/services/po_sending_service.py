"""Getting a purchase order to the supplier: automatic email with the PDF, or WhatsApp / PDF / text by staff.

- place_order() calls auto_email() once the order is committed: if the supplier has an email address and email
  is set up, the PO is emailed in the background, so placing an order never waits for (or fails on) email.
- The "Send to supplier" box uses supplier_message() for the WhatsApp link and the text to copy, email_po() for
  "Send email" / "Retry", and mark_sent() when staff sent it some other way.

sent_* records the first confirmed send; email_* the latest email attempt.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from urllib.parse import quote

from flask import current_app

from app.errors.exceptions import AppError, BadRequestError, ConflictError, NotFoundError
from app.extensions import db
from app.models.enums import PurchaseStatus
from app.models.purchase import PurchaseOrder
from app.models.user import User
from app.schemas.purchase_schemas import SupplierMessageOut
from app.services import audit_service, email_gateway, po_pdf
from app.services.daily_report_service import inr
from app.utils.dates import IST
from app.utils.phone import normalize_mobile
from app.utils.transactions import transaction

# A PO goes to the supplier once it is ordered; until goods are fully in it can still be (re)sent.
SENDABLE = (PurchaseStatus.ORDERED, PurchaseStatus.PARTIALLY_RECEIVED, PurchaseStatus.RECEIVED)
VIA_TEXT = {"email": "email", "whatsapp": "WhatsApp", "phone": "phone", "in_person": "in person", "other": "other"}


def _get(po_id: int) -> PurchaseOrder:
    po = db.session.get(PurchaseOrder, po_id)
    if po is None:
        raise NotFoundError(f"Purchase order {po_id} not found.")
    return po


def _require_sendable(po: PurchaseOrder) -> None:
    if po.status not in SENDABLE:
        raise BadRequestError("Only an ordered purchase order can be sent to the supplier. Place the order first.")


def supplier_mobile(po: PurchaseOrder) -> str | None:
    """The supplier's 10-digit mobile for WhatsApp: phone, else alternate phone. Landlines don't count."""
    for raw in (po.supplier.phone, po.supplier.alt_phone):
        try:
            number = normalize_mobile(raw)
        except AppError:
            continue
        if number:
            return number
    return None


def order_text(po: PurchaseOrder) -> str:
    """The order as plain text, for WhatsApp, SMS or a phone call. Prices stay in the PDF."""
    store = po_pdf.order_store(po)
    lines = [f"*Purchase Order {po.po_number}*"]
    if store:
        lines.append(f"From: {store.name}" + (f" ({store.phone})" if store.phone else ""))
    dates = f"Date: {po.purchase_date:%d %b %Y}"
    if po.expected_delivery_date:
        dates += f" · Deliver by: {po.expected_delivery_date:%d %b %Y}"
    lines.append(dates)
    ship_to = po.shipping_address or (store.address if store else None)
    if ship_to:
        lines.append(f"Deliver to: {ship_to}")
    lines.append("")
    for n, item in enumerate(po.items, start=1):
        uom = item.product.uom.value if item.product and item.product.uom else None
        lines.append(f"{n}. {item.product_name} — {po_pdf.qty_text(item.ordered_qty, uom)}")
    lines.append("")
    lines.append(f"Items: {len(po.items)} · Total: {inr(po.grand_total, keep_paise=True)}")
    if po.notes:
        lines.append(f"Note: {po.notes}")
    lines.append(f"Please quote {po.po_number} on your invoice.")
    return "\n".join(lines)


def supplier_message(po_id: int) -> SupplierMessageOut:
    po = _get(po_id)
    text = order_text(po)
    mobile = supplier_mobile(po)
    return SupplierMessageOut(
        text=text,
        whatsapp_url=f"https://wa.me/91{mobile}?text={quote(text)}" if mobile else None,
        supplier_mobile=mobile,
        supplier_email=(po.supplier.email or "").strip() or None,
        email_configured=email_gateway.is_configured(),
    )


def _email_body(po: PurchaseOrder) -> str:
    store = po_pdf.order_store(po)
    greeting = po.supplier.contact_person or po.supplier.company_name
    lines = [
        f"Dear {greeting},",
        "",
        f"Please find attached our Purchase Order {po.po_number} dated {po.purchase_date:%d %b %Y}.",
    ]
    if po.expected_delivery_date:
        lines.append(f"Expected delivery: {po.expected_delivery_date:%d %b %Y}")
    lines.append(f"Items: {len(po.items)} · Total: {inr(po.grand_total, keep_paise=True)}")
    lines += ["", "Please confirm the order and quote the PO number on your invoice and delivery challan.", "",
              "Regards,"]
    if store:
        lines.append(store.name)
        if store.phone:
            lines.append(f"Ph: {store.phone}")
    return "\n".join(lines)


def email_po(po_id: int, actor_id: int | None) -> PurchaseOrder:
    """Emails the PO PDF to the supplier and records the result on the PO. Never raises for a send failure:
    the reason is saved in email_error for the screen to show."""
    po = _get(po_id)
    actor = db.session.get(User, actor_id) if actor_id else None
    to = (po.supplier.email or "").strip()
    store = po_pdf.order_store(po)
    store_name = store.name if store else ""
    try:
        email_gateway.send(
            to,
            f"Purchase Order {po.po_number}" + (f" from {store_name}" if store_name else ""),
            _email_body(po),
            sender_name=store_name or None,
            attachment=(po_pdf.filename(po), po_pdf.render(po)),
        )
        error = None
    except AppError as exc:
        error = exc.message
    except Exception:  # noqa: BLE001 - a bug while building the email must still show up as "failed"
        current_app.logger.exception("Emailing purchase order %s failed", po.po_number)
        error = "The email could not be prepared. Download the PDF and send it another way."

    with transaction():
        po.email_to = to
        po.email_error = error
        po.email_status = "failed" if error else "sent"
        if not error and po.sent_at is None:
            po.sent_at = datetime.now(timezone.utc)
            po.sent_via = "email"
            po.sent_by_id = actor_id
        audit_service.log(
            actor, "purchase.email_failed" if error else "purchase.emailed", "purchase_order", po.id,
            None, {"to": to, "error": error} if error else {"to": to},
        )
    return po


def email_in_background(po_id: int, actor_id: int | None) -> None:
    """Sends without holding up the request. Tests send inline so results are deterministic."""
    app = current_app._get_current_object()
    if app.testing:
        email_po(po_id, actor_id)
        return

    def run() -> None:
        with app.app_context():
            try:
                email_po(po_id, actor_id)
            finally:
                db.session.remove()

    threading.Thread(target=run, name=f"po-email-{po_id}", daemon=True).start()


def auto_email(po: PurchaseOrder, actor: User | None) -> None:
    """Called after a PO is placed: emails it when the supplier has an address and email is set up."""
    to = (po.supplier.email or "").strip()
    try:
        if not to or not email_gateway.is_configured():
            return
        with transaction():
            po.email_status = "sending"
            po.email_to = to
            po.email_error = None
        email_in_background(po.id, actor.id if actor else None)
    except Exception:  # noqa: BLE001 - the order is already placed; staff can still send it by hand
        current_app.logger.exception("Could not start emailing purchase order %s", po.po_number)


def send_email_now(po_id: int, actor: User | None) -> PurchaseOrder:
    """The "Send email" / "Retry" button: sends while the screen waits, so the result shows at once."""
    po = _get(po_id)
    _require_sendable(po)
    if not (po.supplier.email or "").strip():
        raise BadRequestError("This supplier has no email address. Add it on the supplier page, or send it another way.")
    if not email_gateway.is_configured():
        raise BadRequestError("Email is not set up. Add the mail server in Admin → Settings → Integrations.")
    return email_po(po.id, actor.id if actor else None)


def mark_sent(po_id: int, via: str, actor: User | None) -> PurchaseOrder:
    """Staff sent the PO themselves (WhatsApp, phone, in person…). Recorded once: the first send, by email or by
    hand, is the record and is never overwritten. Sending again (e.g. the email after WhatsApp) is still allowed."""
    po = _get(po_id)
    _require_sendable(po)
    if po.sent_at is not None:
        raise ConflictError(
            f"This PO is already recorded as sent ({VIA_TEXT.get(po.sent_via, po.sent_via)}, "
            f"{po.sent_at.astimezone(IST):%d %b %Y %I:%M %p})."
        )
    with transaction():
        po.sent_at = datetime.now(timezone.utc)
        po.sent_via = via
        po.sent_by_id = actor.id if actor else None
        audit_service.log(
            actor, "purchase.mark_sent", "purchase_order", po.id, None,
            {"sent_via": via, "sent_at": po.sent_at.isoformat()},
        )
    return po
