"""Active discount queries."""
from datetime import datetime

from app.extensions import db
from app.models.discount import Discount
from app.repositories.base_repository import BaseRepository


class DiscountRepository(BaseRepository):
    model = Discount

    def active_for_store(self, store_id: int, now: datetime) -> list[Discount]:
        """Discounts that apply to a bill in this store right now."""
        q = db.select(Discount).where(
            Discount.is_active.is_(True),
            (Discount.store_id.is_(None)) | (Discount.store_id == store_id),
            (Discount.starts_at.is_(None)) | (Discount.starts_at <= now),
            (Discount.ends_at.is_(None)) | (Discount.ends_at > now),
        )
        return list(db.session.scalars(q).all())

    def list_all(self) -> list[Discount]:
        q = db.select(Discount).order_by(Discount.is_active.desc(), Discount.name)
        return list(db.session.scalars(q).all())
