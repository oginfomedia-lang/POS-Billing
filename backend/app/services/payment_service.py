"""Validate and record payments (sum must equal grand total)."""
from __future__ import annotations

from decimal import Decimal

from app.errors.exceptions import AppError
from app.models.enums import PaymentMethod
from app.models.payment import Payment
from app.utils.money import round_money


def build_payment(
    method: str,
    total: Decimal,
    cash_tendered: Decimal | None = None,
    reference: str | None = None,
) -> Payment:
    """Single-method payment for the full bill total. Raises AppError (400) if cash is short."""
    method_enum = PaymentMethod(method)
    total = round_money(total)

    if method_enum is PaymentMethod.CASH:
        if cash_tendered is None:
            raise AppError("Cash tendered is required for cash payments.")
        tendered = round_money(cash_tendered)
        if tendered < total:
            raise AppError(
                f"Cash tendered ({tendered}) is less than the bill total ({total}).",
                details={"total": str(total), "tendered": str(tendered)},
            )
        return Payment(
            method=method_enum,
            amount=total,
            tendered=tendered,
            change_due=round_money(tendered - total),
            reference=reference,
        )

    return Payment(method=method_enum, amount=total, reference=reference)
