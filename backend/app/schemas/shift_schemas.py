"""Shift open/close schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import ShiftStatus


class ShiftOut(BaseModel):
    id: int
    store_id: int
    counter_id: int
    cashier_id: int
    status: ShiftStatus
    opening_cash: Decimal
    opened_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class OpenShiftRequest(BaseModel):
    counter_code: str = Field(..., min_length=1, max_length=10)
    opening_cash: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
