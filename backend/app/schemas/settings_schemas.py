"""System settings schema. Field defaults are the values used until an admin changes them."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.errors.exceptions import AppError
from app.utils.phone import normalize_mobile


class SettingsData(BaseModel):
    receipt_header: str = Field("", max_length=200)  # extra line under the store name, e.g. "Open 8am-10pm"
    rewards_enabled: bool = False
    reward_rupees_per_point: Decimal = Field(Decimal("100"), gt=0, max_digits=12, decimal_places=2)  # ₹100 = 1 point
    reward_block_points: int = Field(100, ge=1, le=100000)       # redeem in blocks of 100 points…
    reward_block_value: Decimal = Field(Decimal("100"), gt=0, max_digits=12, decimal_places=2)  # …each worth ₹100
    receipt_footer: str = Field("Thank you! Visit again.", max_length=200)
    # Printed instead of receipt_footer when the till prints in Marathi ("" = use receipt_footer).
    receipt_footer_mr: str = Field("धन्यवाद! पुन्हा भेट द्या.", max_length=200)
    # FSSAI food licence number printed under the GSTIN on bills. 14 digits; blank = not printed.
    fssai_number: str = Field("", max_length=14)
    low_stock_threshold: Decimal = Field(Decimal("5"), ge=0, max_digits=12, decimal_places=3)
    return_window_days: int = Field(30, ge=0, le=365)  # bills older than this can't be returned
    # Nightly WhatsApp summary of each cashier's collection, sent to the owner's mobiles.
    daily_report_enabled: bool = False
    daily_report_time: str = Field("22:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")  # IST, HH:MM
    daily_report_mobiles: str = Field("", max_length=200)  # comma-separated 10-digit mobiles
    # PDF copy of every paid bill sent on WhatsApp to the customer's mobile (when one is on the bill).
    ebill_enabled: bool = False
    # Weighing-scale stickers for loose items: prefix + item code + weight (grams) or price (paise) + check digit.
    # 29 is taken by our own in-house barcodes (290...).
    scale_prefix: str = Field("20", pattern=r"^2[0-8]$")
    scale_plu_digits: int = Field(5, ge=4, le=6)
    scale_value: Literal["weight", "price"] = "weight"
    # Card / UPI: "razorpay" = Razorpay confirms the money (QR + card machine push, keys in .env);
    # "manual" = the shop's own card machine / UPI QR sticker and the cashier confirms.
    card_upi_mode: Literal["razorpay", "manual"] = "razorpay"

    @field_validator("daily_report_mobiles")
    @classmethod
    def clean_mobiles(cls, value: str) -> str:
        """'+91 98765 43210, 9123456789' -> '9876543210,9123456789'."""
        out: list[str] = []
        for part in value.split(","):
            try:
                mobile = normalize_mobile(part)
            except AppError:
                raise ValueError(f"'{part.strip()}' is not a valid 10-digit mobile number.") from None
            if mobile and mobile not in out:
                out.append(mobile)
        return ",".join(out)

    @field_validator("fssai_number", mode="before")  # before the 14-character limit, so spaces are allowed
    @classmethod
    def clean_fssai(cls, value) -> str:
        value = str(value or "").replace(" ", "").strip()
        if value and (not value.isdigit() or len(value) != 14):
            raise ValueError("FSSAI licence number must be exactly 14 digits.")
        return value

    @property
    def report_mobiles(self) -> list[str]:
        return [m for m in self.daily_report_mobiles.split(",") if m]


class IntegrationsUpdate(BaseModel):
    """Settings → Integrations. Each field: left out / null = keep, "" = remove (back to .env), else the new value."""

    model_config = {"extra": "forbid"}

    RAZORPAY_KEY_ID: str | None = Field(None, max_length=100)
    RAZORPAY_KEY_SECRET: str | None = Field(None, max_length=200)
    RAZORPAY_POS_BASE_URL: str | None = Field(None, max_length=300)
    RAZORPAY_POS_USERNAME: str | None = Field(None, max_length=100)
    RAZORPAY_POS_APP_KEY: str | None = Field(None, max_length=200)
    RAZORPAY_MOCK: bool | None = None
    UPI_QR_EXPIRY_SECONDS: int | Literal[""] | None = None
    PAYTM_MID: str | None = Field(None, max_length=100)
    PAYTM_CLIENT_ID: str | None = Field(None, max_length=100)
    PAYTM_MERCHANT_KEY: str | None = Field(None, max_length=200)
    PAYTM_BASE_URL: str | None = Field(None, max_length=300)
    PAYTM_MOCK: bool | None = None
    WHATSAPP_TOKEN: str | None = Field(None, max_length=1000)
    WHATSAPP_PHONE_NUMBER_ID: str | None = Field(None, max_length=50)
    WHATSAPP_TEMPLATE_NAME: str | None = Field(None, max_length=100)
    WHATSAPP_EBILL_TEMPLATE_NAME: str | None = Field(None, max_length=100)
    WHATSAPP_TEMPLATE_LANG: str | None = Field(None, max_length=20)
    WHATSAPP_MOCK: bool | None = None

    @field_validator("RAZORPAY_POS_BASE_URL", "PAYTM_BASE_URL")
    @classmethod
    def https_only(cls, value: str | None) -> str | None:
        if value and not value.strip().lower().startswith("https://"):
            raise ValueError("Must start with https://")
        return value

    @field_validator("UPI_QR_EXPIRY_SECONDS")
    @classmethod
    def qr_expiry_range(cls, value):
        if isinstance(value, int) and not 120 <= value <= 7200:
            raise ValueError("Razorpay allows 120 to 7200 seconds.")
        return value
