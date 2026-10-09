"""Nightly WhatsApp summary of each cashier's collection, sent to the owner's mobiles.

`flask send-daily-collection` runs every 15 minutes from Windows Task Scheduler and calls run_due():
nothing happens until the configured time has passed, then each store's summary goes to each mobile once.
notification_logs remembers what was sent, so later runs skip it and only retry failures (up to 3 tries).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from flask import current_app

from app.errors.exceptions import AppError
from app.extensions import db
from app.models.enums import NotificationStatus
from app.models.user import User
from app.repositories.notification_repository import NotificationRepository
from app.repositories.store_repository import StoreRepository
from app.schemas.report_schemas import CollectionReportOut, ReportQuery
from app.services import audit_service, report_service, settings_service, whatsapp_gateway
from app.utils.dates import business_date, now_ist
from app.utils.money import round_money
from app.utils.transactions import transaction

KIND = "daily_collection"
KIND_MANUAL = "daily_collection_manual"  # "Send now" from settings; doesn't stop tonight's automatic send
MAX_ATTEMPTS = 3
LINES_LIMIT = 900  # leaves room under WhatsApp's 1024-char limit for the "+N more" note


@dataclass
class SendResult:
    store_name: str
    recipient: str
    status: str
    error: str | None = None


def inr(value) -> str:
    """Indian digit grouping: 1234567.5 -> '₹12,34,567.50'; whole rupees drop the paise."""
    v = round_money(value)
    whole, paise = f"{abs(v):.2f}".split(".")
    head, groups = whole[:-3], [whole[-3:]]
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    text = ",".join(groups) + ("" if paise == "00" else f".{paise}")
    return f"{'-' if v < 0 else ''}₹{text}"


def message_params(store_name: str, day: date, report: CollectionReportOut) -> list[str]:
    """Template variables {{1}}..{{6}}: store, date, per-cashier lines, total, returns, net."""
    lines = []
    for r in report.rows:
        line = f"{r.cashier_name} ({r.counter_code or 'no counter'}): {inr(r.net)}, {r.bills} bills"
        line += f" (Cash {inr(r.cash)}, UPI {inr(r.upi)}, Card {inr(r.card)})"
        if r.refunds:
            line += f", returns {inr(r.refunds)}"
        if r.shift_open:
            line += " [shift still open]"
        elif r.cash_difference:
            line += f" [cash {'short' if r.cash_difference < 0 else 'over'} {inr(abs(r.cash_difference))}]"
        lines.append(line)
    text = ""
    for i, line in enumerate(lines):
        nxt = f"{text} | {line}" if text else line
        if len(nxt) > LINES_LIMIT:
            text += f" | +{len(lines) - i} more, see the app"
            break
        text = nxt
    t = report.totals
    return [
        store_name,
        day.strftime("%d %b %Y"),
        text or "No sales.",
        inr(t.total),
        inr(t.refunds),
        inr(t.net),
    ]


def render(params: list[str]) -> str:
    """Readable copy of the template (kept in notification_logs.body)."""
    store, day, lines, total, refunds, net = params
    return f"Daily collection for {store} on {day}. {lines} Total: {total}, Returns: {refunds}, Net: {net}."


def run_due(now: datetime | None = None) -> list[SendResult]:
    """Sends today's summary if it's switched on and the send time has passed. Safe to call any number of times."""
    settings = settings_service.get_settings()
    if not settings.daily_report_enabled or not settings.report_mobiles:
        return []
    now = now or now_ist()
    hh, mm = map(int, settings.daily_report_time.split(":"))
    if now.time() < time(hh, mm):
        return []
    return send_for_date(now.date(), settings.report_mobiles, KIND)


def send_now(actor: User, day: date | None = None) -> list[SendResult]:
    """'Send now' button: sends again even if already sent. Doesn't count as the nightly send."""
    mobiles = settings_service.get_settings().report_mobiles
    if not mobiles:
        raise AppError("Add at least one mobile number for the daily report first.")
    day = day or business_date()
    results = send_for_date(day, mobiles, KIND_MANUAL, force=True)
    with transaction():
        audit_service.log(
            actor, "daily_report.send", "notification", None, None,
            {"date": day.isoformat(), "sent": sum(r.status == "sent" for r in results), "messages": len(results)},
        )
    return results


def send_for_date(day: date, mobiles: list[str], kind: str = KIND, force: bool = False) -> list[SendResult]:
    """One message per active store per mobile. force = send again even if already sent / out of retries."""
    repo = NotificationRepository()
    stores, _ = StoreRepository().list(per_page=1000, active_only=True)
    results: list[SendResult] = []
    for store in stores:
        report = report_service.collection_report(ReportQuery(store_id=store.id, date_from=day, date_to=day))
        params = message_params(store.name, day, report)
        for mobile in mobiles:
            repo.ensure(kind, day, store.id, mobile)
            db.session.commit()
            log = repo.claim(kind, day, store.id, mobile)  # row lock: a parallel run skips this message
            if log is None:
                continue
            if not force and (log.status == NotificationStatus.SENT or log.attempts >= MAX_ATTEMPTS):
                db.session.commit()  # release the lock
                continue
            try:
                log.provider_message_id = whatsapp_gateway.send_template(mobile, params)
                log.status, log.error, log.sent_at = NotificationStatus.SENT, None, datetime.now(timezone.utc)
            except Exception as exc:  # noqa: BLE001 - one bad send must not stop the others
                if not isinstance(exc, AppError):
                    current_app.logger.exception("Daily report to %s failed", mobile)
                log.status, log.error = NotificationStatus.FAILED, getattr(exc, "message", str(exc))[:500]
            log.attempts += 1
            log.body = render(params)
            db.session.commit()
            results.append(SendResult(store.name, mobile, log.status.value, log.error))
    return results


def recent_logs(limit: int = 30) -> list[dict]:
    return [
        {
            "id": log.id,
            "kind": log.kind,
            "report_date": log.report_date.isoformat(),
            "store_name": store_name,
            "recipient": log.recipient,
            "status": log.status.value,
            "attempts": log.attempts,
            "error": log.error,
            "body": log.body,
            "sent_at": log.sent_at.isoformat() if log.sent_at else None,
            "updated_at": log.updated_at.isoformat(),
        }
        for log, store_name in NotificationRepository().recent(limit)
    ]

