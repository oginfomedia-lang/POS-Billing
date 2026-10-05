"""Audit log queries."""
from app.extensions import db
from app.models.audit_log import AuditLog
from app.repositories.base_repository import BaseRepository


class AuditRepository(BaseRepository):
    model = AuditLog

    def list(
        self,
        page: int = 1,
        per_page: int = 50,
        user_id: int | None = None,
        entity_type: str | None = None,
        action: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        q = db.select(AuditLog)
        if user_id is not None:
            q = q.where(AuditLog.user_id == user_id)
        if entity_type:
            q = q.where(AuditLog.entity_type == entity_type)
        if action:
            q = q.where(AuditLog.action == action)
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery()))
        items = db.session.scalars(
            q.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
        ).all()
        return list(items), total or 0
