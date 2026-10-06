"""Shift open/close schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ShiftOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    store_id: int
    counter_id: int | None
    status: str
    opening_float: Decimal
    expected_cash: Decimal | None
    actual_cash: Decimal | None
    opened_at: datetime
    closed_at: datetime | None


class OpenShiftRequest(BaseModel):
    opening_float: Decimal = Decimal("0")
    store_id: int
    counter_id: int | None = None


class CloseShiftRequest(BaseModel):
    actual_cash: Decimal
