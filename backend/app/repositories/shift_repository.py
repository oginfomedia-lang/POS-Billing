"""Cashier shift queries (active shift, cash totals)."""
from app.extensions import db
from app.models.enums import ShiftStatus
from app.models.shift import CashierShift
from app.repositories.base_repository import BaseRepository


class ShiftRepository(BaseRepository):
    model = CashierShift

    def get_active_for_cashier(self, cashier_id: int) -> CashierShift | None:
        return db.session.scalar(
            db.select(CashierShift).where(
                CashierShift.cashier_id == cashier_id,
                CashierShift.status == ShiftStatus.OPEN,
            )
        )
