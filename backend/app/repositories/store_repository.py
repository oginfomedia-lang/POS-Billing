"""Store and counter queries."""
from app.extensions import db
from app.models.store import Counter, Store
from app.repositories.base_repository import BaseRepository


class StoreRepository(BaseRepository):
    model = Store

    def list(
        self,
        page: int = 1,
        per_page: int = 25,
        active_only: bool = False,
        store_id: int | None = None,
    ) -> tuple[list[Store], int]:
        q = db.select(Store)
        if store_id is not None:
            q = q.where(Store.id == store_id)
        if active_only:
            q = q.where(Store.is_active.is_(True))
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery()))
        items = db.session.scalars(
            q.order_by(Store.name).offset((page - 1) * per_page).limit(per_page)
        ).all()
        return list(items), total or 0


class CounterRepository(BaseRepository):
    model = Counter

    def get_by_code(self, store_id: int, code: str) -> Counter | None:
        """Codes are unique per store (Store A and Store B can both have C01)."""
        return db.session.scalar(db.select(Counter).where(Counter.store_id == store_id, Counter.code == code))

    def get_by_label_ci(self, store_id: int, label: str) -> Counter | None:
        return db.session.scalar(
            db.select(Counter).where(Counter.store_id == store_id, db.func.lower(Counter.label) == label.lower())
        )

    def list_for_store(self, store_id: int, active_only: bool = False) -> list[Counter]:
        q = db.select(Counter).where(Counter.store_id == store_id)
        if active_only:
            q = q.where(Counter.is_active.is_(True))
        return list(db.session.scalars(q.order_by(Counter.code)).all())
