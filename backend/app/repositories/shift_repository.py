"""Cashier shift queries."""
from app.extensions import db
from app.models.shift import CashierShift
from app.models.enums import ShiftStatus
from app.repositories.base_repository import BaseRepository


class ShiftRepository(BaseRepository):
    model = CashierShift

    def get_active_shift(self, user_id: int) -> CashierShift | None:
        return db.session.scalar(
            db.select(CashierShift)
            .where(CashierShift.user_id == user_id)
            .where(CashierShift.status == ShiftStatus.OPEN)
        )

    def list_for_user(
        self, user_id: int, page: int = 1, per_page: int = 25
    ) -> tuple[list[CashierShift], int]:
        q = db.select(CashierShift).where(CashierShift.user_id == user_id)
        total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery()))
        items = db.session.scalars(
            q.order_by(CashierShift.opened_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        ).all()
        return list(items), total or 0
