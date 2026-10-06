"""System settings schema. Field defaults are the values used until an admin changes them."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class SettingsData(BaseModel):
    receipt_header: str = Field("", max_length=200)  # extra line under the store name, e.g. "Open 8am-10pm"
    receipt_footer: str = Field("Thank you! Visit again.", max_length=200)
    low_stock_threshold: Decimal = Field(Decimal("5"), ge=0, max_digits=12, decimal_places=3)
