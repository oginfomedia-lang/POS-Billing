"""User and role queries."""
from app.extensions import db
from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository):
    model = User

    def get_by_username(self, username: str) -> User | None:
        return db.session.scalar(db.select(User).where(User.username == username))

    def list(
        self,
        page: int = 1,
        per_page: int = 25,
        active_only: bool = False,
        is_active: bool | None = None,
        store_id: int | None = None,
    ) -> tuple[list[User], int]:
        q = db.select(User)
        if store_id is not None:
            q = q.where(User.store_id == store_id)
        if active_only:
            q = q.where(User.is_active.is_(True))
        if is_active is not None:
            q = q.where(User.is_active.is_(is_active))
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery()))
        items = db.session.scalars(
            q.order_by(User.username).offset((page - 1) * per_page).limit(per_page)
        ).all()
        return list(items), total or 0
