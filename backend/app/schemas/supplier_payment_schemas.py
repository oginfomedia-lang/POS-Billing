"""Schemas for Supplier Payment module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import SupplierPaymentMethod, SupplierPaymentType


class PaymentAllocationIn(BaseModel):
    invoice_id: int
    allocated_amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)


class SupplierPaymentCreate(BaseModel):
    supplier_id: int
    store_id: int | None = None
    payment_date: date
    amount: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    payment_type: SupplierPaymentType = SupplierPaymentType.PAYMENT
    payment_method: SupplierPaymentMethod = SupplierPaymentMethod.BANK_TRANSFER
    reference_number: str | None = Field(None, max_length=100)
    bank_account: str | None = Field(None, max_length=200)
    notes: str | None = None
    allocations: list[PaymentAllocationIn] = []


class PaymentAllocationOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    payment_id: int
    invoice_id: int
    invoice_number: str = ""
    allocated_amount: Decimal


class SupplierPaymentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    supplier_id: int
    supplier_name: str = ""
    store_id: int | None
    payment_date: date
    amount: Decimal
    payment_type: SupplierPaymentType
    payment_method: SupplierPaymentMethod
    reference_number: str | None
    bank_account: str | None
    notes: str | None
    is_voided: bool
    voided_at: datetime | None
    allocations: list[PaymentAllocationOut] = []
    unallocated_amount: Decimal = Decimal("0")  # advance not yet applied to an invoice
    created_at: datetime
    updated_at: datetime


class ApplyAdvanceIn(BaseModel):
    """Put (part of) an advance against invoices that arrived later."""

    allocations: list[PaymentAllocationIn] = Field(..., min_length=1)
