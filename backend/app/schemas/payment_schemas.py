"""Payment schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models.enums import PaymentMethod


class PaymentOut(BaseModel):
    id: int
    method: PaymentMethod
    amount: Decimal
    reference: str | None
    tendered: Decimal | None
    change_due: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}
