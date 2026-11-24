"""Customer Udhari (Store Credit / Khata) service.

Handles:
- Checking credit limits and posting credit sales during POS checkout.
- Recording repayments when customers clear their dues.
- Querying customer Khata passbook and balances.
"""
from __future__ import annotations

from decimal import Decimal

from app.errors.exceptions import AppError, NotFoundError
from app.extensions import db
from app.models.customer import CreditTransaction, Customer
from app.models.enums import CreditTxnType, PaymentMethod
from app.models.returns import SaleReturn
from app.models.sale import Sale
from app.models.user import User
from app.repositories.customer_repository import CustomerRepository
from app.repositories.shift_repository import ShiftRepository
from app.schemas.customer_schemas import CustomerCreditInfoOut
from app.services import audit_service
from app.utils.money import round_money
from app.utils.phone import normalize_mobile
from app.utils.transactions import transaction

ZERO = Decimal("0.00")


def get_credit_info(mobile: str) -> CustomerCreditInfoOut:
    """Fetch live credit balance and remaining limit for a phone number."""
    number = normalize_mobile(mobile)
    if number is None:
        raise AppError("Enter a valid 10-digit mobile number.")

    customer = CustomerRepository().get_by_mobile(number)
    if customer is None:
        return CustomerCreditInfoOut(
            mobile=number,
            name=None,
            registered=False,
            credit_balance=ZERO,
            credit_limit=None,
            available_credit=None,
        )

    balance = round_money(customer.credit_balance)
    limit = round_money(customer.credit_limit) if customer.credit_limit is not None else None
    available = round_money(limit - balance) if limit is not None else None

    return CustomerCreditInfoOut(
        mobile=customer.mobile,
        name=customer.name,
        registered=True,
        credit_balance=balance,
        credit_limit=limit,
        available_credit=available,
    )


def settle_sale_credit(sale: Sale, actor: User) -> None:
    """Called inside billing_service.complete() inside its DB transaction.

    If any payment on the bill is on CREDIT, verifies the customer and credit limit,
    increments credit_balance, and adds a passbook row in credit_transactions.
    """
    credit_payments = [p for p in sale.payments if p.method == PaymentMethod.CREDIT]
    if not credit_payments:
        return

    credit_amount = round_money(sum((p.amount for p in credit_payments), ZERO))
    if credit_amount <= ZERO:
        return

    # Udhari requires a mobile number to attach the debt to, and a name to know who owes it.
    if not sale.customer_mobile:
        raise AppError("A customer mobile number is required to make a sale on Udhari (credit).")

    repo = CustomerRepository()
    customer = repo.get_or_create_for_update(sale.customer_mobile)
    if sale.customer_name:
        customer.name = sale.customer_name
    if not customer.name:
        raise AppError("Enter the customer's name to make a sale on Udhari (credit).")
    sale.customer_id = customer.id

    # Check credit limit rule
    current_balance = round_money(customer.credit_balance)
    if customer.credit_limit is not None:
        limit = round_money(customer.credit_limit)
        if (current_balance + credit_amount) > limit:
            raise AppError(
                f"Credit limit of ₹{limit} exceeded! "
                f"Current dues: ₹{current_balance}, this bill: ₹{credit_amount}."
            )

    # Update balance and write passbook entry
    customer.credit_balance = round_money(current_balance + credit_amount)
    txn = CreditTransaction(
        customer_id=customer.id,
        store_id=sale.store_id,
        sale_id=sale.id,
        txn_type=CreditTxnType.UDHARI,
        amount=credit_amount,
        balance_after=customer.credit_balance,
        note=f"Bill {sale.bill_number}",
        created_by_id=actor.id,
    )
    db.session.add(txn)


def sale_on_credit(sale: Sale) -> bool:
    """True when the bill was paid on udhari (its money is owed, not in the drawer or the bank)."""
    return any(p.method == PaymentMethod.CREDIT for p in sale.payments)


def reverse_for_return(sale: Sale, ret: SaleReturn, actor: User) -> None:
    """Goods returned from a bill paid on udhari: the refund comes off the customer's dues, no cash changes hands.

    Called inside return_service.create_return()'s transaction, after the return has its id. If the customer has
    already paid more than they now owe, the balance goes below zero: the store holds that money for them, and it
    is used up by their next udhari bill (the passbook shows it).
    """
    if not sale.customer_id:
        raise AppError("This udhari bill has no customer account, so the refund can't go back on the khata.")
    amount = round_money(ret.refund_amount)
    if amount <= ZERO:
        return
    customer = db.session.get(Customer, sale.customer_id, with_for_update=True)
    customer.credit_balance = round_money(round_money(customer.credit_balance) - amount)
    db.session.add(CreditTransaction(
        customer_id=customer.id,
        store_id=ret.store_id,
        sale_id=sale.id,
        return_id=ret.id,
        txn_type=CreditTxnType.RETURN,
        amount=-amount,
        balance_after=customer.credit_balance,
        note=f"Return {ret.return_number} of bill {sale.bill_number}",
        created_by_id=actor.id,
    ))


def record_repayment(
    customer_id: int,
    store_id: int,
    amount: Decimal,
    payment_method: str,
    reference: str | None,
    note: str | None,
    actor: User,
) -> CreditTransaction:
    """Record customer repayment towards their outstanding dues.

    Never more than is owed (a typing slip would otherwise leave the shop owing the customer). Cash taken by a
    cashier with an open shift in this store is in their drawer, so it is tied to the shift and counted in its
    expected cash.
    """
    amount = round_money(amount)
    if amount <= ZERO:
        raise AppError("Repayment amount must be greater than zero.")

    shift_id = None
    if payment_method == "cash":
        shift = ShiftRepository().get_active_shift(actor.id)
        if shift is not None and shift.store_id == store_id:
            shift_id = shift.id

    with transaction():
        customer = db.session.get(Customer, customer_id, with_for_update=True)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found.")

        current_balance = round_money(customer.credit_balance)
        if current_balance <= ZERO:
            raise AppError(f"{customer.name or customer.mobile} has no udhari dues to pay.")
        if amount > current_balance:
            raise AppError(f"The dues are only ₹{current_balance}. Take at most that.")
        new_balance = round_money(current_balance - amount)
        customer.credit_balance = new_balance

        txn = CreditTransaction(
            customer_id=customer.id,
            store_id=store_id,
            shift_id=shift_id,
            txn_type=CreditTxnType.PAYMENT,
            amount=-amount,
            balance_after=new_balance,
            payment_method=payment_method,
            reference=reference,
            note=note or "Udhari Repayment",
            created_by_id=actor.id,
        )
        db.session.add(txn)
        audit_service.log(
            actor, "customer.udhari_repay", "customer", customer.id,
            {"credit_balance": str(current_balance)},
            {"credit_balance": str(new_balance), "amount": str(amount), "method": payment_method,
             "shift_id": shift_id},
        )

    return txn


def cash_repayments_for_shift(shift_id: int) -> Decimal:
    """Udhari paid back in cash into this shift's drawer."""
    total = db.session.scalar(
        db.select(db.func.coalesce(db.func.sum(-CreditTransaction.amount), 0)).where(
            CreditTransaction.shift_id == shift_id,
            CreditTransaction.txn_type == CreditTxnType.PAYMENT,
            CreditTransaction.payment_method == "cash",
        )
    )
    return Decimal(total)


def update_name(customer_id: int, name: str | None, actor: User) -> Customer:
    """Add or correct a customer's name. A customer who owes money (udhari) must keep a name."""
    name = " ".join((name or "").split()) or None
    with transaction():
        customer = db.session.get(Customer, customer_id, with_for_update=True)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found.")
        if name is None and round_money(customer.credit_balance) > ZERO:
            raise AppError("This customer owes money on udhari, so the name can't be removed.")
        old = customer.name
        customer.name = name
        audit_service.log(actor, "customer.name", "customer", customer.id, {"name": old}, {"name": name})
    return customer


def update_credit_limit(customer_id: int, credit_limit: Decimal | None, actor: User) -> Customer:
    """Set or remove customer's maximum allowable credit limit."""
    with transaction():
        customer = db.session.get(Customer, customer_id, with_for_update=True)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} not found.")

        old = customer.credit_limit
        customer.credit_limit = round_money(credit_limit) if credit_limit is not None else None
        audit_service.log(
            actor, "customer.credit_limit", "customer", customer.id,
            {"credit_limit": None if old is None else str(old)},
            {"credit_limit": None if customer.credit_limit is None else str(customer.credit_limit)},
        )
    return customer


def customer_credit_ledger(customer_id: int, page: int = 1, per_page: int = 50) -> tuple[list[CreditTransaction], int]:
    """Retrieve full passbook statement for a customer."""
    customer = db.session.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError(f"Customer {customer_id} not found.")

    q = db.select(CreditTransaction).where(CreditTransaction.customer_id == customer_id)
    total = db.session.scalar(db.select(db.func.count()).select_from(q.subquery())) or 0
    q = q.order_by(CreditTransaction.id.desc()).offset((page - 1) * per_page).limit(per_page)
    items = db.session.scalars(q).all()
    return list(items), total