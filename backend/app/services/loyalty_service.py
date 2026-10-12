"""Reward points: earn on paid bills, redeem in blocks as a bill discount, take back on returns.

Rules (settings_schemas.SettingsData):
  earn   = 1 point per full ₹reward_rupees_per_point of what the customer paid (incl. GST)
  redeem = blocks of reward_block_points points, each worth ₹reward_block_value off the bill
           (taken off before GST, like a fixed bill offer)

Points are only RESERVED on an open bill (sale.points_redeemed). They are taken from the customer in
settle_sale(), which runs inside billing_service.complete()'s transaction — so a voided/held bill
needs no undo, and a failed bill never loses anyone's points.
"""
from __future__ import annotations

from decimal import Decimal

from app.errors.exceptions import AppError, ConflictError, NotFoundError
from app.models.customer import Customer
from app.models.enums import RewardTxnType
from app.models.returns import SaleReturn
from app.models.sale import Sale, SaleItem
from app.models.user import User
from app.repositories.customer_repository import CustomerRepository
from app.schemas.customer_schemas import RewardInfoOut
from app.schemas.settings_schemas import SettingsData
from app.services import pricing_service, settings_service
from app.utils.dates import now_ist
from app.utils.money import round_money, to_decimal
from app.utils.phone import normalize_mobile

ZERO = pricing_service.ZERO


def points_for(amount, s: SettingsData) -> int:
    """1 point per full ₹100 paid: ₹1,250 -> 12, ₹99 -> 0 (always rounded down)."""
    return max(int(to_decimal(amount) // s.reward_rupees_per_point), 0)


def rewards_for_mobile(mobile: str) -> RewardInfoOut:
    """Balance for the payment screen. Read-only: doesn't register anyone."""
    number = normalize_mobile(mobile)
    if number is None:
        raise AppError("Enter the customer's mobile number.")
    s = settings_service.get_settings()
    customer = CustomerRepository().get_by_mobile(number)
    balance = customer.points_balance if customer else 0
    return RewardInfoOut(
        mobile=number,
        registered=customer is not None,
        enabled=s.rewards_enabled,
        points_balance=balance,
        block_points=s.reward_block_points,
        block_value=s.reward_block_value,
        max_blocks=balance // s.reward_block_points if s.rewards_enabled else 0,
    )


def reward_lines(sale: Sale, items: list[SaleItem], room: list[Decimal]) -> list[Decimal]:
    """Spreads the reserved reward over the bill's lines (before GST), like a fixed bill offer.

    room[i] = what's left of line i after its manual discount and the automatic offer.
    If items were removed and the bill is now smaller than the reward, fewer blocks are used
    (sale.points_redeemed is lowered), so the reward can never be more than the bill.
    """
    if not sale.points_redeemed:
        sale.reward_discount = ZERO
        return [ZERO] * len(items)
    s = settings_service.get_settings()
    blocks = sale.points_redeemed // s.reward_block_points if s.rewards_enabled else 0
    payable = sum(room, ZERO)
    while blocks and s.reward_block_value * blocks > payable:
        blocks -= 1
    sale.points_redeemed = blocks * s.reward_block_points
    value = round_money(s.reward_block_value * blocks)
    sale.reward_discount = value
    return pricing_service.allocate(value, room)


def settle_sale(sale: Sale, actor: User) -> None:
    """Registers the customer, takes the redeemed points, gives the earned ones. Called inside complete()."""
    if not sale.customer_mobile:
        return
    s = settings_service.get_settings()
    repo = CustomerRepository()
    customer = repo.get_or_create_for_update(sale.customer_mobile)  # first paid bill = registration
    note = f"Bill {sale.bill_number}"

    if sale.points_redeemed:
        # Checked again here, under the row lock: the points may have been used on another counter meanwhile.
        if customer.points_balance < sale.points_redeemed:
            raise ConflictError(
                f"The customer now has only {customer.points_balance} points. Remove the redemption and try again."
            )
        repo.add_txn(customer, RewardTxnType.REDEEM, -sale.points_redeemed, sale_id=sale.id, note=note, user=actor)

    sale.points_earned = points_for(sale.total, s) if s.rewards_enabled else 0  # on what was actually paid
    if sale.points_earned:
        repo.add_txn(customer, RewardTxnType.EARN, sale.points_earned, sale_id=sale.id, note=note, user=actor)

    now = now_ist()
    sale.customer_id = customer.id
    customer.visit_count += 1
    customer.total_spent += sale.total
    customer.first_visit_at = customer.first_visit_at or now
    customer.last_visit_at = now


def reverse_for_return(sale: Sale, ret: SaleReturn, actor: User) -> None:
    """Takes back earned points in proportion to the money refunded.

    Worked out on the running total of refunds, so several partial returns never take back more than
    was earned. Redeemed points are not given back (usual shop policy). The balance never goes below 0.
    """
    if not sale.customer_id or not sale.points_earned or not sale.total:
        return
    repo = CustomerRepository()
    customer = repo.lock(sale.customer_id)
    refunded = to_decimal(repo.refunded_for_sale(sale.id))
    should_be_back = min(sale.points_earned, int(sale.points_earned * refunded / sale.total))
    take = min(should_be_back - repo.reversed_for_sale(sale.id), customer.points_balance)
    if take > 0:
        repo.add_txn(
            customer, RewardTxnType.REVERSE, -take, sale_id=sale.id, return_id=ret.id,
            note=f"Return {ret.return_number}", user=actor,
        )


def list_customers(search: str | None, page: int, per_page: int) -> tuple[list[Customer], int]:
    return CustomerRepository().search(search, page, per_page)


def customer_ledger(customer_id: int, page: int, per_page: int):
    if CustomerRepository().get_by_id(customer_id) is None:
        raise NotFoundError(f"Customer {customer_id} not found.")
    return CustomerRepository().ledger(customer_id, page, per_page)