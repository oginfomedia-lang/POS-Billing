"""Customer, reward-points and redeem schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import CreditTxnType, RewardTxnType


class RewardInfoOut(BaseModel):
    """What the payment screen shows after the mobile is typed."""

    mobile: str
    registered: bool  # False = first visit; the customer is created when this bill is paid
    enabled: bool  # reward points switched on in settings
    points_balance: int
    block_points: int  # e.g. 100 points…
    block_value: Decimal  # …= ₹100 off
    max_blocks: int  # how many blocks the balance allows (the bill amount may allow fewer)


class RedeemPointsRequest(BaseModel):
    blocks: int = Field(..., ge=0, le=1000)  # 0 removes the redemption


class CustomerOut(BaseModel):
    id: int
    mobile: str
    name: str | None
    points_balance: int
    lifetime_earned: int
    lifetime_redeemed: int
    credit_balance: Decimal
    credit_limit: Decimal | None
    total_spent: Decimal
    visit_count: int
    first_visit_at: datetime | None
    last_visit_at: datetime | None

    model_config = {"from_attributes": True}


class RewardTxnOut(BaseModel):
    id: int
    txn_type: RewardTxnType
    points: int
    balance_after: int
    note: str | None
    sale_id: int | None
    return_id: int | None
    created_at: datetime

    model_config = {"from_attributes": True}

class CustomerCreditInfoOut(BaseModel):
    """What the POS checkout screen fetches when mobile is entered."""
    mobile: str
    name: str | None
    registered: bool
    credit_balance: Decimal
    credit_limit: Decimal | None
    available_credit: Decimal | None  # None = unlimited, otherwise (credit_limit - credit_balance)


class CreditRepaymentRequest(BaseModel):
    """When a customer repays dues (Khata settlement)."""
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    payment_method: Literal["cash", "upi", "card", "bank"] = "cash"
    reference: str | None = Field(None, max_length=100)
    note: str | None = Field(None, max_length=255)
    store_id: int | None = None  # head office only; everyone else repays at their own store


class CreditLimitUpdateRequest(BaseModel):
    """Admin updates customer credit limit."""
    credit_limit: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)


class CreditTxnOut(BaseModel):
    """One row in the customer's Khata passbook."""
    id: int
    txn_type: CreditTxnType
    amount: Decimal
    balance_after: Decimal
    payment_method: str | None
    reference: str | None
    note: str | None
    sale_id: int | None
    return_id: int | None
    shift_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}