"""Schemas for Supplier Invoice module."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import InvoiceVerificationStatus, SupplierInvoiceStatus


class SupplierInvoiceCreate(BaseModel):
    supplier_id: int
    purchase_order_id: int | None = None
    store_id: int | None = None
    invoice_number: str = Field(..., min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None
    subtotal: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    tax_amount: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    other_charges: Decimal = Field(Decimal("0"), ge=0, max_digits=12, decimal_places=2)
    grand_total: Decimal = Field(..., gt=0, max_digits=12, decimal_places=2)
    notes: str | None = None
    grn_ids: list[int] = []


class SupplierInvoiceUpdate(BaseModel):
    invoice_number: str | None = Field(None, min_length=1, max_length=100)
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    tax_amount: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    other_charges: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    grand_total: Decimal | None = Field(None, gt=0, max_digits=12, decimal_places=2)
    notes: str | None = None
    verification_status: InvoiceVerificationStatus | None = None
    grn_ids: list[int] | None = None


class SupplierInvoiceOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    supplier_id: int
    supplier_name: str = ""
    purchase_order_id: int | None
    po_number: str | None = None
    store_id: int | None
    invoice_number: str
    invoice_date: date
    due_date: date | None
    subtotal: Decimal
    tax_amount: Decimal
    other_charges: Decimal
    grand_total: Decimal
    amount_paid: Decimal
    outstanding: Decimal = Decimal("0")
    payment_status: SupplierInvoiceStatus
    verification_status: InvoiceVerificationStatus
    notes: str | None
    grn_ids: list[int] = []
    created_at: datetime
    updated_at: datetime


class SupplierInvoiceListParams(BaseModel):
    supplier_id: int | None = None
    payment_status: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    page: int = 1
    per_page: int = 25
