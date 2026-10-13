"""Supplier request/response schemas (Pydantic v2)."""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, field_validator

from app.models.enums import PaymentTerms


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v if v else None


def _validate_gstin(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip().upper()
    if not re.fullmatch(r"\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]", v):
        raise ValueError("Invalid GSTIN format (15 characters, e.g. 27AAPFU0939F1ZV).")
    return v


def _validate_pan(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip().upper()
    if not re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", v):
        raise ValueError("Invalid PAN format (10 characters, e.g. AAPFU0939F).")
    return v


def _validate_phone(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip()
    if not re.fullmatch(r"[\d\s+\-()]{7,20}", v):
        raise ValueError("Invalid phone number format (7–20 digits/spaces/+/-/parentheses).")
    return v


def _validate_email(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip().lower()
    if not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", v):
        raise ValueError("Invalid email address format.")
    return v


class SupplierCreate(BaseModel):
    supplier_code: str | None = None
    company_name: str
    contact_person: str | None = None
    phone: str | None = None
    alt_phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    pan: str | None = None
    billing_address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    country: str = "India"
    payment_terms: PaymentTerms = PaymentTerms.NET_30
    notes: str | None = None

    @field_validator("company_name", mode="before")
    @classmethod
    def require_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Company name is required.")
        return v

    _phone = field_validator("phone", mode="before")(classmethod(lambda cls, v: _validate_phone(v)))
    _alt_phone = field_validator("alt_phone", mode="before")(classmethod(lambda cls, v: _validate_phone(v)))
    _email = field_validator("email", mode="before")(classmethod(lambda cls, v: _validate_email(v)))
    _gstin = field_validator("gstin", mode="before")(classmethod(lambda cls, v: _validate_gstin(v)))
    _pan = field_validator("pan", mode="before")(classmethod(lambda cls, v: _validate_pan(v)))
    _clean_fields = field_validator(
        "contact_person", "billing_address", "city", "state", "pincode", "notes", mode="before"
    )(classmethod(lambda cls, v: _clean(v)))


class SupplierUpdate(BaseModel):
    company_name: str | None = None
    contact_person: str | None = None
    phone: str | None = None
    alt_phone: str | None = None
    email: str | None = None
    gstin: str | None = None
    pan: str | None = None
    billing_address: str | None = None
    city: str | None = None
    state: str | None = None
    pincode: str | None = None
    country: str | None = None
    payment_terms: PaymentTerms | None = None
    notes: str | None = None
    is_active: bool | None = None

    @field_validator("company_name", mode="before")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Company name cannot be empty.")
        return v

    _phone = field_validator("phone", mode="before")(classmethod(lambda cls, v: _validate_phone(v)))
    _alt_phone = field_validator("alt_phone", mode="before")(classmethod(lambda cls, v: _validate_phone(v)))
    _email = field_validator("email", mode="before")(classmethod(lambda cls, v: _validate_email(v)))
    _gstin = field_validator("gstin", mode="before")(classmethod(lambda cls, v: _validate_gstin(v)))
    _pan = field_validator("pan", mode="before")(classmethod(lambda cls, v: _validate_pan(v)))
    _clean_fields = field_validator(
        "contact_person", "billing_address", "city", "state", "pincode", "notes", mode="before"
    )(classmethod(lambda cls, v: _clean(v)))


class SupplierOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    supplier_code: str
    company_name: str
    contact_person: str | None
    phone: str | None
    alt_phone: str | None
    email: str | None
    gstin: str | None
    pan: str | None
    billing_address: str | None
    city: str | None
    state: str | None
    pincode: str | None
    country: str
    payment_terms: PaymentTerms
    notes: str | None
    is_active: bool
    product_count: int = 0
    created_at: datetime
    updated_at: datetime


class SupplierDashboard(BaseModel):
    total: int
    active: int
    inactive: int
    products_linked: int


class SupplierProductCreate(BaseModel):
    product_id: int
    supplier_product_code: str | None = None
    purchase_price: float | None = None
    min_order_qty: float | None = None
    lead_time_days: int | None = None
    is_preferred: bool = False
    notes: str | None = None
    is_active: bool = True

    _clean = field_validator("supplier_product_code", "notes", mode="before")(
        classmethod(lambda cls, v: _clean(v))
    )


class SupplierProductUpdate(BaseModel):
    supplier_product_code: str | None = None
    purchase_price: float | None = None
    min_order_qty: float | None = None
    lead_time_days: int | None = None
    is_preferred: bool | None = None
    notes: str | None = None
    is_active: bool | None = None


class SupplierProductOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    supplier_id: int
    product_id: int
    product_name: str = ""
    product_sku: str | None = None
    supplier_product_code: str | None
    purchase_price: float | None
    last_purchase_price: float | None
    min_order_qty: float | None
    lead_time_days: int | None
    is_preferred: bool
    notes: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SupplierSummary(BaseModel):
    supplier_id: int
    total_po_value: float
    total_received_value: float  # goods accepted on all GRNs, at PO rates
    not_invoiced_value: float = 0.0  # received but no supplier invoice entered yet
    total_invoiced: float  # invoice totals as billed
    total_payable: float = 0.0  # what is owed on those invoices (never more than the goods received)
    total_paid: float
    outstanding_balance: float  # opening balance + payable − paid − unused advance (negative = advance left over)
    advance_balance: float  # advance paid and not yet applied to an invoice
    overdue_amount: float
    invoice_count: int
    disputed_count: int = 0  # invoices whose amount differs from the goods received
    payment_count: int


class SupplierLedgerEntry(BaseModel):
    date: str
    entry_type: str
    reference: str
    description: str
    debit: float
    credit: float
    balance: float
