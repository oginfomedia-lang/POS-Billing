"""Payment schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.models.enums import PaymentIntentStatus, PaymentMethod


class PaymentOut(BaseModel):
    id: int
    method: PaymentMethod
    amount: Decimal
    reference: str | None
    tendered: Decimal | None
    change_due: Decimal | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StartPaymentRequest(BaseModel):
    """Card = push the bill amount to this counter's card machine; upi = make a fixed-amount Razorpay QR."""

    method: Literal["card", "upi"]


class PaymentIntentOut(BaseModel):
    """One Razorpay attempt. The client polls it until status is no longer 'pending'."""

    id: int
    sale_id: int
    method: PaymentMethod
    amount: Decimal
    status: PaymentIntentStatus
    qr_image_url: str | None
    failure_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
