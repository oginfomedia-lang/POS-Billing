"""Supplier request/response schemas (Pydantic v2)."""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, field_validator, model_validator

from app.errors.exceptions import AppError
from app.models.enums import PaymentTerms
from app.utils.phone import normalize_mobile


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


def _validate_mobile(v: str | None) -> str | None:
    """Primary phone: a 10-digit Indian mobile ('+91 98765-43210' is saved as '9876543210')."""
    try:
        return normalize_mobile(v)
    except AppError:
        raise ValueError("Enter a valid 10-digit mobile number (starting with 6, 7, 8 or 9).") from None


def _validate_alt_phone(v: str | None) -> str | None:
    """Alternate phone: a 10-digit mobile, or a landline with its STD code (0 + 10 digits, e.g. 02024567890)."""
    if v is None:
        return None
    digits = re.sub(r"[\s\-()]", "", str(v))
    if not digits:
        return None
    if re.fullmatch(r"0\d{10}", digits):
        return digits
    try:
        return normalize_mobile(digits)
    except AppError:
        raise ValueError(
            "Enter a 10-digit mobile number, or a landline with its STD code (11 digits, e.g. 02024567890)."
        ) from None


def _limit(max_len: int, label: str):
    def check(v: str | None) -> str | None:
        v = _clean(v)
        if v is not None and len(v) > max_len:
            raise ValueError(f"{label} can be at most {max_len} characters.")
        return v
    return check


def _check_pincode(values):
    """Indian PIN codes are 6 digits and never start with 0."""
    pincode = values.pincode
    country = (values.country or "India").strip().lower()
    if pincode and country == "india" and not re.fullmatch(r"[1-9]\d{5}", pincode):
        raise ValueError("Enter a valid 6-digit PIN code.")
    if pincode and not re.fullmatch(r"[A-Za-z0-9 \-]{3,10}", pincode):
        raise ValueError("Enter a valid postal code.")
    return values


def _validate_email(v: str | None) -> str | None:
    if not v:
        return None
    v = v.strip().lower()
    if len(v) > 200 or not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", v):
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
        if len(v) > 200:
            raise ValueError("Company name can be at most 200 characters.")
        return v

    _phone = field_validator("phone", mode="before")(classmethod(lambda cls, v: _validate_mobile(v)))
    _alt_phone = field_validator("alt_phone", mode="before")(classmethod(lambda cls, v: _validate_alt_phone(v)))
    _email = field_validator("email", mode="before")(classmethod(lambda cls, v: _validate_email(v)))
    _gstin = field_validator("gstin", mode="before")(classmethod(lambda cls, v: _validate_gstin(v)))
    _pan = field_validator("pan", mode="before")(classmethod(lambda cls, v: _validate_pan(v)))
    _contact = field_validator("contact_person", mode="before")(classmethod(lambda cls, v: _limit(100, "Contact person")(v)))
    _city = field_validator("city", mode="before")(classmethod(lambda cls, v: _limit(100, "City")(v)))
    _state = field_validator("state", mode="before")(classmethod(lambda cls, v: _limit(100, "State")(v)))
    _country = field_validator("country", mode="before")(classmethod(lambda cls, v: _limit(100, "Country")(v)))
    _address = field_validator("billing_address", mode="before")(classmethod(lambda cls, v: _limit(500, "Address")(v)))
    _notes = field_validator("notes", mode="before")(classmethod(lambda cls, v: _limit(2000, "Notes")(v)))
    _pin = field_validator("pincode", mode="before")(classmethod(lambda cls, v: _clean(v)))
    _pin_check = model_validator(mode="after")(_check_pincode)


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
            if len(v) > 200:
                raise ValueError("Company name can be at most 200 characters.")
        return v

    _phone = field_validator("phone", mode="before")(classmethod(lambda cls, v: _validate_mobile(v)))
    _alt_phone = field_validator("alt_phone", mode="before")(classmethod(lambda cls, v: _validate_alt_phone(v)))
    _email = field_validator("email", mode="before")(classmethod(lambda cls, v: _validate_email(v)))
    _gstin = field_validator("gstin", mode="before")(classmethod(lambda cls, v: _validate_gstin(v)))
    _pan = field_validator("pan", mode="before")(classmethod(lambda cls, v: _validate_pan(v)))
    _contact = field_validator("contact_person", mode="before")(classmethod(lambda cls, v: _limit(100, "Contact person")(v)))
    _city = field_validator("city", mode="before")(classmethod(lambda cls, v: _limit(100, "City")(v)))
    _state = field_validator("state", mode="before")(classmethod(lambda cls, v: _limit(100, "State")(v)))
    _country = field_validator("country", mode="before")(classmethod(lambda cls, v: _limit(100, "Country")(v)))
    _address = field_validator("billing_address", mode="before")(classmethod(lambda cls, v: _limit(500, "Address")(v)))
    _notes = field_validator("notes", mode="before")(classmethod(lambda cls, v: _limit(2000, "Notes")(v)))
    _pin = field_validator("pincode", mode="before")(classmethod(lambda cls, v: _clean(v)))
    _pin_check = model_validator(mode="after")(_check_pincode)


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
