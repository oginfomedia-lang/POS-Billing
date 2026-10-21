"""Audit log queries."""
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.base_repository import BaseRepository

# Words that mean "everyone with this role" in the user filter.
_ROLE_WORDS = {
    word: role
    for role in UserRole
    for word in (role.value, role.value + "s")
}


class AuditRepository(BaseRepository):
    model = AuditLog

    def list(
        self,
        page: int = 1,
        per_page: int = 50,
        user_id: int | None = None,
        entity_type: str | None = None,
        action: str | None = None,
        user: str | None = None,
    ) -> tuple[list[AuditLog], int]:
        """All filters combine (AND).
        user: a role ("admin", "managers", ...) = everyone with that role; otherwise part of the username or
              full name ("rah" finds rahul_a / Rahul Patil).
        action: part of the action ("sale" finds sale.complete, sale.void, ...)."""
        q = db.select(AuditLog)
        if user_id is not None:
            q = q.where(AuditLog.user_id == user_id)
        if entity_type:
            q = q.where(AuditLog.entity_type == entity_type)
        if action and action.strip():
            q = q.where(AuditLog.action.icontains(action.strip(), autoescape=True))
        if user and user.strip():
            text = user.strip()
            role = _ROLE_WORDS.get(text.lower())
            people = db.select(User.id).where(
                User.role == role if role else
                (User.username.icontains(text, autoescape=True) | User.full_name.icontains(text, autoescape=True))
            )
            match = AuditLog.user_id.in_(people)
            if role is None:  # also the name saved on the entry (survives the user being removed)
                match = match | AuditLog.username.icontains(text, autoescape=True)
            q = q.where(match)
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery()))
        items = db.session.scalars(
            q.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
        ).all()
        return list(items), total or 0

    def filter_values(self) -> dict:
        """What the filter boxes suggest: actions and record types that occur, and the people in the log."""
        actions = db.session.scalars(db.select(AuditLog.action).distinct().order_by(AuditLog.action)).all()
        types = db.session.scalars(db.select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)).all()
        people = db.session.execute(
            db.select(User.username, User.full_name, User.role)
            .where(User.id.in_(db.select(AuditLog.user_id).where(AuditLog.user_id.is_not(None)).distinct()))
            .order_by(User.username)
        ).all()
        return {
            "actions": list(actions),
            "entity_types": list(types),
            "roles": [r.value for r in UserRole],
            "users": [{"username": u, "full_name": n, "role": r.value} for u, n, r in people],
        }
