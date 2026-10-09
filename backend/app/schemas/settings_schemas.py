"""System settings schema. Field defaults are the values used until an admin changes them."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class SettingsData(BaseModel):
    receipt_header: str = Field("", max_length=200)  # extra line under the store name, e.g. "Open 8am-10pm"
    rewards_enabled: bool = False
    reward_rupees_per_point: Decimal = Field(Decimal("100"), gt=0, max_digits=12, decimal_places=2)  # ₹100 = 1 point
    reward_block_points: int = Field(100, ge=1, le=100000)       # redeem in blocks of 100 points…
    reward_block_value: Decimal = Field(Decimal("100"), gt=0, max_digits=12, decimal_places=2)  # …each worth ₹100
    receipt_footer: str = Field("Thank you! Visit again.", max_length=200)
    low_stock_threshold: Decimal = Field(Decimal("5"), ge=0, max_digits=12, decimal_places=3)
    return_window_days: int = Field(30, ge=0, le=365)  # bills older than this can't be returned
