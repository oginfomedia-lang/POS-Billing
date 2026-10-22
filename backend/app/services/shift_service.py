"""open_shift(), get_active_shift(), close_shift() with expected cash and difference, shift_bills()."""
from datetime import datetime, timezone
from decimal import Decimal

from app.errors.exceptions import ConflictError, NotFoundError
from app.models.shift import CashierShift
from app.models.enums import PaymentMethod, SaleStatus, ShiftStatus, UserRole
from app.models.store import Store
from app.models.user import User
from app.extensions import db
from app.utils.store_scope import is_head_office, require_store_access
from app.repositories.payment_repository import PaymentRepository
from app.repositories.return_repository import ReturnRepository
from app.repositories.sale_repository import SaleRepository
from app.repositories.shift_repository import ShiftRepository
from app.repositories.store_repository import CounterRepository
from app.schemas.shift_schemas import (
    CloseShiftRequest,
    OpenShiftRequest,
    ShiftBillOut,
    ShiftBillPaymentOut,
    ShiftBillsOut,
    ShiftOut,
    ShiftReturnOut,
    ShiftSummaryOut,
)
from app.utils.phone import mask_mobile
from app.utils.transactions import transaction


def open_shift(actor: User, data: OpenShiftRequest) -> CashierShift:
    """A shift runs in the actor's own store (head office may open one in any store), on a counter of that store."""
    user_id = actor.id
    store = db.session.get(Store, data.store_id)
    if store is None or not store.is_active:
        raise NotFoundError(f"Store {data.store_id} not found.")
    require_store_access(actor, data.store_id)
    repo = ShiftRepository()
    existing = repo.get_active_shift(user_id)
    if existing:
        raise ConflictError("A shift is already open for this user.")
    if data.counter_id is not None:
        counter = CounterRepository().get_by_id(data.counter_id)
        if counter is None or counter.store_id != data.store_id or not counter.is_active:
            raise NotFoundError(f"Counter {data.counter_id} not found in store {data.store_id}.")
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


def require_active_shift(user_id: int) -> CashierShift:
    """For billing: 409 (not 404) so the POS knows to send the cashier to Open Shift."""
    shift = ShiftRepository().get_active_shift(user_id)
    if shift is None:
        raise ConflictError("No open shift. Open a shift before billing.")
    return shift


def close_shift(shift_id: int, user_id: int, data: CloseShiftRequest) -> CashierShift:
    shift = _get_shift_or_404(shift_id)
    if shift.user_id != user_id:
        raise NotFoundError("Shift not found.")
    if shift.status != ShiftStatus.OPEN:
        raise ConflictError("Shift is already closed.")
    _require_no_unfinished_bills(shift)

    shift.expected_cash = expected_cash(shift)
    shift.actual_cash = data.actual_cash
    shift.status = ShiftStatus.CLOSED
    shift.closed_at = datetime.now(timezone.utc)
    with transaction():
        pass
    return shift


def _require_no_unfinished_bills(shift: CashierShift) -> None:
    """A held bill (or the bill being rung up) can only be finished in the shift it was started in, so the
    shift can't close while one is left: it would be stuck, and its goods / money unaccounted for.
    Empty bills don't count (the till always has one ready)."""
    repo = SaleRepository()
    held = [s for s in repo.list_held(shift.id) if s.items]
    current = [s for s in repo.list_open(shift.id, shift.user_id) if s.items]
    if held or current:
        parts = []
        if held:
            parts.append(f"{len(held)} bill{'s are' if len(held) > 1 else ' is'} on hold")
        if current:
            parts.append("the current bill has items")
        raise ConflictError(
            f"Can't close the shift: {' and '.join(parts)}. Finish (pay) or void "
            f"{'them' if len(held) + len(current) > 1 else 'it'} first.",
            {"held_bills": len(held), "open_bills": len(current)},
        )


def expected_cash(shift: CashierShift) -> Decimal:
    """Expected cash in the drawer = opening float + cash taken on this shift's paid bills
    − cash paid out for returns during this shift. Card and UPI never go in the drawer."""
    return (
        shift.opening_float
        + PaymentRepository().cash_total_for_shift(shift.id)
        - ReturnRepository().cash_refunds_for_shift(shift.id)
    )


def shift_bills(shift_id: int, actor: User) -> ShiftBillsOut:
    """Every bill and refund on one shift, with the cash the drawer should hold.

    A cashier sees only their own shifts; an admin / manager any shift of their store (head office: all).
    """
    shift = _get_shift_or_404(shift_id)
    if not _can_view_shift(shift, actor):
        raise NotFoundError("Shift not found.")

    sales = SaleRepository().list_for_shift(shift.id)
    paid = [s for s in sales if s.status == SaleStatus.PAID]
    refunded = ReturnRepository().refunded_by_sale([s.id for s in paid])
    by_method = PaymentRepository().totals_by_method_for_shift(shift.id)
    returns = ReturnRepository().list_for_shift(shift.id)
    zero = Decimal("0.00")
    cash_refunds = sum((r.refund_amount for r in returns if r.refund_method == PaymentMethod.CASH), zero)

    bills = [
        ShiftBillOut(
            id=s.id,
            bill_number=s.bill_number,
            status=s.status.value,
            completed_at=s.completed_at,
            created_at=s.created_at,
            total=s.total,
            items_count=len(s.items),
            payments=[ShiftBillPaymentOut(method=p.method.value, amount=p.amount) for p in s.payments],
            customer_mobile=mask_mobile(s.customer_mobile),
            return_count=refunded.get(s.id, (0, zero))[0],
            refunded=refunded.get(s.id, (0, zero))[1],
        )
        # Paid bills, and held / voided ones that had something on them (not the empty drafts).
        for s in sales
        if s.status == SaleStatus.PAID or (s.status in (SaleStatus.HELD, SaleStatus.VOIDED) and s.items)
    ]
    summary = ShiftSummaryOut(
        paid_bills=len(paid),
        held_bills=sum(1 for b in bills if b.status == SaleStatus.HELD.value),
        voided_bills=sum(1 for b in bills if b.status == SaleStatus.VOIDED.value),
        sales_total=sum((s.total for s in paid), zero),
        cash_sales=by_method.get(PaymentMethod.CASH, zero),
        card_sales=by_method.get(PaymentMethod.CARD, zero),
        upi_sales=by_method.get(PaymentMethod.UPI, zero),
        returns=len(returns),
        cash_refunds=cash_refunds,
        other_refunds=sum((r.refund_amount for r in returns if r.refund_method != PaymentMethod.CASH), zero),
        opening_float=shift.opening_float,
        # A closed shift keeps the figure it was closed with.
        expected_cash=shift.expected_cash if shift.expected_cash is not None else expected_cash(shift),
    )
    return ShiftBillsOut(
        shift=ShiftOut.model_validate(shift),
        cashier_name=shift.user.full_name or shift.user.username,
        counter_code=shift.counter.code if shift.counter else None,
        summary=summary,
        bills=bills,
        returns=[
            ShiftReturnOut(
                id=r.id,
                return_number=r.return_number,
                bill_number=r.sale.bill_number if r.sale else None,
                created_at=r.created_at,
                refund_method=r.refund_method.value,
                refund_amount=r.refund_amount,
            )
            for r in returns
        ],
    )


def _can_view_shift(shift: CashierShift, actor: User) -> bool:
    """Own shift; any shift for head office (admins); the store's shifts for its manager."""
    if shift.user_id == actor.id or is_head_office(actor):
        return True
    return actor.role is UserRole.MANAGER and actor.store_id == shift.store_id


def _get_shift_or_404(shift_id: int) -> CashierShift:
    shift = ShiftRepository().get_by_id(shift_id)
    if shift is None:
        raise NotFoundError(f"Shift {shift_id} not found.")
    return shift
