"""NotificationLog queries. One row per (kind, report_date, store, recipient); see uq_notification_once."""
from datetime import date

from sqlalchemy.dialects.postgresql import insert

from app.extensions import db
from app.models.enums import NotificationStatus
from app.models.notification import NotificationLog
from app.models.store import Store


class NotificationRepository:
    def ensure(self, kind: str, report_date: date, store_id: int, recipient: str) -> None:
        """Creates the row if it doesn't exist yet (safe when two runs race)."""
        stmt = insert(NotificationLog).values(
            kind=kind, report_date=report_date, store_id=store_id, recipient=recipient,
            status=NotificationStatus.PENDING, attempts=0,
            created_at=db.func.now(), updated_at=db.func.now(),
        )
        db.session.execute(stmt.on_conflict_do_nothing(constraint="uq_notification_once"))

    def claim(self, kind: str, report_date: date, store_id: int, recipient: str) -> NotificationLog | None:
        """Locks the row until the next commit. None = another run is sending this message right now."""
        q = (
            db.select(NotificationLog)
            .where(
                NotificationLog.kind == kind,
                NotificationLog.report_date == report_date,
                NotificationLog.store_id == store_id,
                NotificationLog.recipient == recipient,
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        return db.session.scalars(q).first()

    def recent(self, limit: int = 30) -> list[tuple[NotificationLog, str]]:
        q = (
            db.select(NotificationLog, Store.name)
            .join(Store, Store.id == NotificationLog.store_id)
            .order_by(NotificationLog.updated_at.desc())
            .limit(limit)
        )
        return [tuple(r) for r in db.session.execute(q).all()]
