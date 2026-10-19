"""User schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.enums import UserRole


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-z0-9_]+$")
    full_name: str = Field(..., min_length=1, max_length=150)
    pin: str = Field(..., min_length=4, max_length=12, pattern=r"^[A-Za-z0-9]{4,12}$")
    role: UserRole
    store_id: int | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=1, max_length=150)
    role: UserRole | None = None
    store_id: int | None = None
    is_active: bool | None = None


class PinReset(BaseModel):
    new_pin: str = Field(..., min_length=4, max_length=12, pattern=r"^[A-Za-z0-9]{4,12}$")
