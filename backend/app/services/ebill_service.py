"""WhatsApp e-bill: a PDF copy of the paid bill sent to the customer's mobile.

The backend sends it, not the counter app, so it goes out even when the receipt printer is broken:
- billing_service.complete() calls queue() inside the sale's transaction (a PENDING notification_logs row),
  then send_in_background() once committed, so checkout never waits for WhatsApp.
- `flask send-ebills` (Task Scheduler, every 5 minutes) retries failed / unsent ones: retry_due().
- The bill screen's "Send on WhatsApp" button calls resend(), also to a number typed in at that moment.
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import current_app

from app.errors.exceptions import AppError
from app.extensions import db
from app.models.enums import NotificationStatus
from app.models.notification import NotificationLog
from app.models.sale import Sale
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.services import audit_service, ebill_pdf, integration_settings_service, settings_service, whatsapp_gateway
from app.services.daily_report_service import SendResult, inr
from app.utils.dates import IST
from app.utils.phone import mask_mobile, normalize_mobile
from app.utils.transactions import transaction

MAX_ATTEMPTS = 3
RETRY_WINDOW = timedelta(days=2)  # older unsent e-bills are given up on


def queue(sale: Sale) -> bool:
    """Inside the completing sale's transaction: records that this bill's e-bill is due. True = queued."""
    if not sale.customer_mobile or not settings_service.get_settings().ebill_enabled:
        return False
    NotificationRepository().ensure_ebill(
        sale.id, sale.store_id, sale.completed_at.astimezone(IST).date(), sale.customer_mobile
    )
    return True


def send_in_background(sale_id: int, recipient: str) -> None:
    """Sends without holding up the request. Tests send inline so results are deterministic."""
    app = current_app._get_current_object()
    if app.testing:
        send(sale_id, recipient)
        return

    def run() -> None:
        with app.app_context():
            try:
                send(sale_id, recipient)
            finally:
                db.session.remove()

    threading.Thread(target=run, name=f"ebill-{sale_id}", daemon=True).start()


def message_params(receipt) -> list[str]:
    """Template variables {{1}}..{{4}}: store, bill number, date, total."""
    return [
        receipt.store_name,
        receipt.bill_number,
        receipt.completed_at.astimezone(IST).strftime("%d %b %Y"),
        inr(receipt.total, keep_paise=True),
    ]


def send(sale_id: int, recipient: str, force: bool = False) -> SendResult | None:
    """Sends one e-bill. force = send again even if already sent / out of retries. None = nothing done."""
    from app.services import receipt_service  # receipt_service imports billing_service, which imports us

    repo = NotificationRepository()
    log = repo.claim_ebill(sale_id, recipient)  # row lock: a parallel retry skips this message
    if log is None:
        db.session.rollback()
        return None
    if not force and (log.status == NotificationStatus.SENT or log.attempts >= MAX_ATTEMPTS):
        db.session.commit()  # release the lock
        return None
    receipt = None
    try:
        receipt = receipt_service.build_receipt(sale_id)
        params = message_params(receipt)
        filename = f"Bill-{receipt.bill_number}.pdf"
        pdf = ebill_pdf.render(receipt)
        if integration_settings_service.value("WHATSAPP_MOCK") and not current_app.testing:
            _save_mock_copy(filename, pdf)
        media_id = whatsapp_gateway.upload_media(pdf, filename)
        log.provider_message_id = whatsapp_gateway.send_template(
            recipient, params, template=integration_settings_service.value("WHATSAPP_EBILL_TEMPLATE_NAME"),
            document=(media_id, filename),
        )
        log.status, log.error, log.sent_at = NotificationStatus.SENT, None, datetime.now(timezone.utc)
        log.body = f"E-bill {receipt.bill_number} ({params[3]}) from {receipt.store_name}, {filename}"
    except Exception as exc:  # noqa: BLE001 - recorded on the row and retried later
        if not isinstance(exc, AppError):
            current_app.logger.exception("E-bill for sale %s to %s failed", sale_id, recipient)
        log.status, log.error = NotificationStatus.FAILED, getattr(exc, "message", str(exc))[:500]
    log.attempts += 1
    db.session.commit()
    return SendResult(receipt.store_name if receipt else "", recipient, log.status.value, log.error)


def _save_mock_copy(filename: str, pdf: bytes) -> None:
    """Mock mode: keep the PDF in backend/logs/ebills/ so it can be opened and checked."""
    folder = Path(current_app.root_path).parent / "logs" / "ebills"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / filename).write_bytes(pdf)
    except OSError:
        current_app.logger.warning("Could not save mock e-bill %s", filename)


def retry_due() -> list[SendResult]:
    """E-bills that failed or never went (internet down, server restarted): try again, up to MAX_ATTEMPTS."""
    since = datetime.now(timezone.utc) - RETRY_WINDOW
    results = []
    for sale_id, recipient in NotificationRepository().due_ebills(since, MAX_ATTEMPTS):
        result = send(sale_id, recipient)
        if result:
            results.append(result)
    return results


def resend(sale_id: int, mobile: str | None, actor: User) -> dict | None:
    """Cashier's "Send on WhatsApp": to the typed number, or the bill's customer mobile. Waits for the result.

    Works even with the e-bill setting off. Doesn't change the bill's customer (loyalty points stay put).
    """
    from app.services.billing_service import get_sale

    sale = get_sale(sale_id)
    if sale.bill_number is None or sale.completed_at is None:
        raise AppError("An e-bill can only be sent for a completed bill.")
    recipient = normalize_mobile(mobile) or sale.customer_mobile
    if not recipient:
        raise AppError("Enter the customer's mobile number.")
    NotificationRepository().ensure_ebill(sale.id, sale.store_id, sale.completed_at.astimezone(IST).date(), recipient)
    db.session.commit()
    result = send(sale.id, recipient, force=True)
    if result is None:
        raise AppError("This e-bill is being sent right now. Try again in a moment.")
    with transaction():
        audit_service.log(
            actor, "ebill.send", "sale", sale.id, None,
            {"bill_number": sale.bill_number, "to": mask_mobile(recipient), "status": result.status},
        )
    return status_for_sale(sale.id)


def status_for_sale(sale_id: int) -> dict | None:
    """Latest e-bill for this bill, for the bill screen."""
    log: NotificationLog | None = NotificationRepository().latest_for_sale(sale_id)
    if log is None:
        return None
    return {
        "status": log.status.value,
        "recipient": mask_mobile(log.recipient),
        "error": log.error,
        "sent_at": log.sent_at.isoformat() if log.sent_at else None,
    }
