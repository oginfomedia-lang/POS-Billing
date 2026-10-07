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
    max_discount_amount: Decimal | None
    buy_qty: int | None
    get_qty: int | None
    starts_at: datetime | None
    ends_at: datetime | None
    is_active: bool
    product_name: str | None = None  # read from Discount.product_name property
    category_name: str | None = None

    model_config = {"from_attributes": True}


class DiscountIn(BaseModel):
    """Used for both create and update (the admin form always sends every field)."""

    name: str = Field(..., min_length=1, max_length=100)
    discount_type: DiscountType
    value: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    scope: DiscountScope
    product_id: int | None = None
    category_id: int | None = None
    store_id: int | None = None
    min_bill_amount: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    max_discount_amount: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    buy_qty: int | None = Field(None, ge=1, le=999)
    get_qty: int | None = Field(None, ge=1, le=999)
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
        if self.discount_type in (DiscountType.BUY_X_GET_Y, DiscountType.QTY_PRICE):
            if self.scope is DiscountScope.BILL:
                raise ValueError("'Buy X get Y' and quantity-price offers apply to a product or category, not the whole bill.")
        if self.discount_type is DiscountType.BUY_X_GET_Y:
            if not self.buy_qty or not self.get_qty:
                raise ValueError("Enter how many the customer buys and how many they get free.")
            self.value = Decimal("0")  # no rupee/percent value for this type
        elif self.discount_type is DiscountType.QTY_PRICE:
            if not self.buy_qty or self.buy_qty < 2:
                raise ValueError("Enter a bundle size of 2 or more.")
            if self.value <= 0:
                raise ValueError("Enter the bundle price.")
            self.get_qty = None
        else:
            if self.value <= 0:
                raise ValueError("Enter a discount value greater than 0.")
            self.buy_qty = self.get_qty = None
        if self.discount_type is not DiscountType.PERCENTAGE:
            self.max_discount_amount = None  # the cap only makes sense for % offers
        # Drop targets that don't match the scope so stale ids from the form aren't saved.
        if self.scope is not DiscountScope.PRODUCT:
            self.product_id = None
        if self.scope is not DiscountScope.CATEGORY:
            self.category_id = None
        if self.scope is not DiscountScope.BILL:
            self.min_bill_amount = None
        return self
