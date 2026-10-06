"""open_shift(), get_active_shift(), close_shift() with expected cash and difference."""
from __future__ import annotations

from app.errors.exceptions import AppError, ConflictError, NotFoundError
from app.extensions import db
from app.models.enums import ShiftStatus
from app.models.shift import CashierShift
from app.models.user import User
from app.repositories.shift_repository import ShiftRepository
from app.repositories.store_repository import CounterRepository
from app.schemas.shift_schemas import OpenShiftRequest
from app.services import audit_service
from app.utils.transactions import transaction


def open_shift(data: OpenShiftRequest, actor: User) -> CashierShift:
    repo = ShiftRepository()
    if repo.get_active_for_cashier(actor.id):
        raise ConflictError("You already have an open shift.")
    if actor.store_id is None:
        raise AppError("Your user is not assigned to a store.")

    counter = CounterRepository().get_by_code(data.counter_code)
    if counter is None or counter.store_id != actor.store_id or not counter.is_active:
        raise NotFoundError(f"Counter '{data.counter_code}' not found in your store.")

    shift = CashierShift(
        store_id=actor.store_id,
        counter_id=counter.id,
        cashier_id=actor.id,
        status=ShiftStatus.OPEN,
        opening_cash=data.opening_cash,
    )
    with transaction():
        repo.add(shift)
        db.session.flush()
        audit_service.log(
            actor, "shift.open", "shift", shift.id, None,
            {"counter_id": counter.id, "opening_cash": str(data.opening_cash)},
        )
    return shift


def get_active_shift(actor: User) -> CashierShift | None:
    return ShiftRepository().get_active_for_cashier(actor.id)


def require_active_shift(actor: User) -> CashierShift:
    shift = get_active_shift(actor)
    if shift is None:
        raise ConflictError("No open shift. Open a shift before billing.")
    return shift
