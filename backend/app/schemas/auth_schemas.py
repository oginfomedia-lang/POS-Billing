"""Login request/response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    pin: str = Field(..., min_length=4, max_length=8)


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: UserRole
    store_id: int | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
