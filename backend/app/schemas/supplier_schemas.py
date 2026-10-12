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
