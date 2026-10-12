"""NotificationLog queries.

Daily report: one row per (kind, report_date, store, recipient), sale_id NULL; see uq_notification_once.
E-bill: one row per (sale, recipient); see uq_notification_ebill.
"""
from datetime import date, datetime

from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.enums import NotificationStatus
from app.models.notification import NotificationLog
from app.models.store import Store

EBILL = "ebill"


class NotificationRepository:
    def ensure(self, kind: str, report_date: date, store_id: int, recipient: str) -> None:
        """Creates the row if it doesn't exist yet (safe when two runs race)."""
        stmt = insert(NotificationLog).values(
            kind=kind, report_date=report_date, store_id=store_id, recipient=recipient,
            status=NotificationStatus.PENDING, attempts=0,
            created_at=db.func.now(), updated_at=db.func.now(),
        )
        db.session.execute(stmt.on_conflict_do_nothing(
            index_elements=["kind", "report_date", "store_id", "recipient"],
            index_where=NotificationLog.sale_id.is_(None),
        ))

    def claim(self, kind: str, report_date: date, store_id: int, recipient: str) -> NotificationLog | None:
        """Locks the row until the next commit. None = another run is sending this message right now."""
        q = (
            db.select(NotificationLog)
            .where(
                NotificationLog.kind == kind,
                NotificationLog.report_date == report_date,
                NotificationLog.store_id == store_id,
                NotificationLog.recipient == recipient,
                NotificationLog.sale_id.is_(None),
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return db.session.scalars(q).first()

    def recent(self, limit: int = 30) -> list[tuple[NotificationLog, str]]:
        """Latest daily-report messages (e-bills are shown on their bill instead)."""
        q = (
            db.select(NotificationLog, Store.name)
            .join(Store, Store.id == NotificationLog.store_id)
            .where(NotificationLog.sale_id.is_(None))
            .order_by(NotificationLog.updated_at.desc())
            .limit(limit)
        )
        return [tuple(r) for r in db.session.execute(q).all()]

    # --- e-bills ---

    def ensure_ebill(self, sale_id: int, store_id: int, report_date: date, recipient: str) -> None:
        stmt = insert(NotificationLog).values(
            kind=EBILL, report_date=report_date, store_id=store_id, sale_id=sale_id, recipient=recipient,
            status=NotificationStatus.PENDING, attempts=0,
            created_at=db.func.now(), updated_at=db.func.now(),
        )
        db.session.execute(stmt.on_conflict_do_nothing(
            index_elements=["sale_id", "recipient"], index_where=NotificationLog.sale_id.isnot(None),
        ))

    def claim_ebill(self, sale_id: int, recipient: str) -> NotificationLog | None:
        """Locks the row until the next commit. None = another thread is sending this e-bill right now."""
        q = (
            db.select(NotificationLog)
            .where(NotificationLog.sale_id == sale_id, NotificationLog.recipient == recipient)
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return db.session.scalars(q).first()

    def latest_for_sale(self, sale_id: int) -> NotificationLog | None:
        q = (
            db.select(NotificationLog)
            .where(NotificationLog.sale_id == sale_id)
            .order_by(NotificationLog.updated_at.desc(), NotificationLog.id.desc())
            .limit(1)
        )
        return db.session.scalars(q).first()

    def due_ebills(self, since: datetime, max_attempts: int) -> list[tuple[int, str]]:
        """(sale_id, recipient) of e-bills not sent yet that still have tries left."""
        q = (
            db.select(NotificationLog.sale_id, NotificationLog.recipient)
            .where(
                NotificationLog.sale_id.isnot(None),
                NotificationLog.status != NotificationStatus.SENT,
                NotificationLog.attempts < max_attempts,
                NotificationLog.created_at >= since,
            )
            .order_by(NotificationLog.id)
        )
        return [tuple(r) for r in db.session.execute(q).all()]
