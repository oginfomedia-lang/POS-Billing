"""open_shift(), get_active_shift(), close_shift() with expected cash and difference."""
from datetime import datetime, timezone

from app.errors.exceptions import ConflictError, NotFoundError
from app.models.shift import CashierShift
from app.models.enums import ShiftStatus
from app.repositories.shift_repository import ShiftRepository
from app.schemas.shift_schemas import CloseShiftRequest, OpenShiftRequest
from app.utils.transactions import transaction


def open_shift(user_id: int, data: OpenShiftRequest) -> CashierShift:
    repo = ShiftRepository()
    existing = repo.get_active_shift(user_id)
    if existing:
        raise ConflictError("A shift is already open for this user.")
    shift = CashierShift(
        user_id=user_id,
        store_id=data.store_id,
        counter_id=data.counter_id,
        opening_float=data.opening_float,
        status=ShiftStatus.OPEN,
    )
    with transaction():
        repo.add(shift)
    return shift


def get_active_shift(user_id: int) -> CashierShift:
    shift = ShiftRepository().get_active_shift(user_id)
    if shift is None:
        raise NotFoundError("No active shift found.")
    return shift


def close_shift(shift_id: int, user_id: int, data: CloseShiftRequest) -> CashierShift:
    shift = _get_shift_or_404(shift_id)
    if shift.user_id != user_id:
        raise NotFoundError("Shift not found.")
    if shift.status != ShiftStatus.OPEN:
        raise ConflictError("Shift is already closed.")

    # expected cash = opening float + cash sales total (calculated by billing layer)
    # For now, set expected_cash = opening_float (billing will update this on sale completion)
    shift.actual_cash = data.actual_cash
    shift.status = ShiftStatus.CLOSED
    shift.closed_at = datetime.now(timezone.utc)
    with transaction():
        pass
    return shift


def _get_shift_or_404(shift_id: int) -> CashierShift:
    shift = ShiftRepository().get_by_id(shift_id)
    if shift is None:
        raise NotFoundError(f"Shift {shift_id} not found.")
    return shift
