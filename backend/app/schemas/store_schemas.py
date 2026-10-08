"""Store and counter schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StoreOut(BaseModel):
    id: int
    name: str
    address: str | None
    phone: str | None
    gstin: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class StoreCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    address: str | None = None
    phone: str | None = Field(None, max_length=20)
    gstin: str | None = Field(None, max_length=20)


class StoreUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=150)
    address: str | None = None
    phone: str | None = Field(None, max_length=20)
    gstin: str | None = Field(None, max_length=20)
    is_active: bool | None = None


class CounterOut(BaseModel):
    id: int
    code: str
    label: str
    store_id: int
    is_active: bool
    created_at: datetime
    eds_device_id: str | None=None

    model_config = {"from_attributes": True}


class CounterCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=10, pattern=r"^[A-Z0-9]+$")
    label: str = Field(..., min_length=1, max_length=100)
    edc_device_id: str | None = Field(None, max_length=100)


class CounterUpdate(BaseModel):
    label: str | None = Field(None, min_length=1, max_length=100)
    is_active: bool | None = None
    edc_device_id: str | None = Field(None, max_length=100)
