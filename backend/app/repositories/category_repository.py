"""Category queries."""
from app.extensions import db
from app.models.category import Category
from app.repositories.base_repository import BaseRepository


class CategoryRepository(BaseRepository):
    model = Category

    def list(
        self,
        page: int = 1,
        per_page: int = 100,
        active_only: bool = False,
    ) -> tuple[list[Category], int]:
        q = db.select(Category)
        if active_only:
            q = q.where(Category.is_active.is_(True))
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery()))
        items = db.session.scalars(
            q.order_by(Category.name).offset((page - 1) * per_page).limit(per_page)
        ).all()
        return list(items), total or 0

    def get_by_name(self, name: str) -> Category | None:
        return db.session.scalar(db.select(Category).where(Category.name == name))

    def get_by_name_ci(self, name: str) -> Category | None:
        """Same name ignoring capitals ("Dairy" = "dairy")."""
        return db.session.scalar(db.select(Category).where(db.func.lower(Category.name) == name.lower()).limit(1))

    def parent_map(self) -> dict[int, int | None]:
        """{category_id: parent_id} for every category, in one query (used to find sub-categories)."""
        return dict(db.session.execute(db.select(Category.id, Category.parent_id)).all())
