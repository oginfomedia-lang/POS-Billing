"""Shared helpers: get_by_id, add, list with pagination."""
from app.extensions import db


class BaseRepository:
    model = None

    def get_by_id(self, id_: int):
        return db.session.get(self.model, id_)

    def add(self, instance):
        db.session.add(instance)
        return instance

    def list(self, page: int = 1, per_page: int = 25) -> tuple[list, int]:
        q = db.select(self.model)
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery()))
        items = db.session.scalars(q.offset((page - 1) * per_page).limit(per_page)).all()
        return list(items), total or 0
