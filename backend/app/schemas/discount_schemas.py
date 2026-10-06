"""Discount schemas."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models.enums import DiscountScope, DiscountType


class DiscountOut(BaseModel):
    id: int
    name: str
    discount_type: DiscountType
    value: Decimal
    scope: DiscountScope
    product_id: int | None
    category_id: int | None
    store_id: int | None
    min_bill_amount: Decimal | None
    starts_at: datetime | None
    ends_at: datetime | None
    is_active: bool

    model_config = {"from_attributes": True}


class DiscountIn(BaseModel):
    """Used for both create and update (the admin form always sends every field)."""

    name: str = Field(..., min_length=1, max_length=100)
    discount_type: DiscountType
    value: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    scope: DiscountScope
    product_id: int | None = None
    category_id: int | None = None
    store_id: int | None = None
    min_bill_amount: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def check_scope(self) -> "DiscountIn":
        if self.discount_type is DiscountType.PERCENTAGE and self.value > 100:
            raise ValueError("A percentage discount can't be more than 100.")
        if self.scope is DiscountScope.PRODUCT and self.product_id is None:
            raise ValueError("Choose the product this discount applies to.")
        if self.scope is DiscountScope.CATEGORY and self.category_id is None:
            raise ValueError("Choose the category this discount applies to.")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("End time must be after the start time.")
        # Drop targets that don't match the scope so stale ids from the form aren't saved.
        if self.scope is not DiscountScope.PRODUCT:
            self.product_id = None
        if self.scope is not DiscountScope.CATEGORY:
            self.category_id = None
        if self.scope is not DiscountScope.BILL:
            self.min_bill_amount = None
        return self
