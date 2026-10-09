"""Customer, reward-points and redeem schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import RewardTxnType


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