"""Barcode formatting, generation, calculation and parsing utilities."""
import re
from typing import NamedTuple


class VariableWeightData(NamedTuple):
    sku: str
    weight_grams: int
    weight_kg: float


def calculate_ean13_checksum(payload_12_digits: str) -> str:
    """Calculate EAN-13 Luhn modulo 10 checksum digit for a 12-digit string."""
    if len(payload_12_digits) != 12 or not payload_12_digits.isdigit():
        raise ValueError("Payload for EAN-13 checksum must be exactly 12 numeric digits.")

    odd_sum = sum(int(payload_12_digits[i]) for i in range(0, 12, 2))
    even_sum = sum(int(payload_12_digits[i]) for i in range(1, 12, 2))
    total = odd_sum + (even_sum * 3)
    checksum = (10 - (total % 10)) % 10
    return str(checksum)


def validate_ean13(barcode: str) -> bool:
    """Check if a barcode is a valid 13-digit EAN-13 barcode with correct checksum."""
    if len(barcode) != 13 or not barcode.isdigit():
        return False
    expected_checksum = calculate_ean13_checksum(barcode[:12])
    return barcode[12] == expected_checksum


def generate_inhouse_barcode(product_id_or_sku: int | str, prefix: str = "290") -> str:
    """Generate a 13-digit DMart Premia style in-house barcode.

    Structure: prefix (3 digits, default '290') + 9-digit zero-padded product ID/SKU + 1 checksum digit.
    """
    prefix_str = str(prefix).strip()
    if len(prefix_str) != 3 or not prefix_str.isdigit():
        raise ValueError("In-house prefix must be 3 numeric digits.")

    # Extract digits from product_id_or_sku
    raw_str = str(product_id_or_sku)
    digits_only = re.sub(r"\D", "", raw_str)
    if not digits_only:
        digits_only = str(abs(hash(raw_str)))

    # Take rightmost 9 digits or zero pad to 9 digits
    sku_9digit = digits_only[-9:].zfill(9)
    payload_12 = f"{prefix_str}{sku_9digit}"
    checksum = calculate_ean13_checksum(payload_12)
    return f"{payload_12}{checksum}"


def parse_variable_weight_barcode(barcode: str) -> VariableWeightData | None:
    """Parse 13-digit variable-weight scale-embedded barcode starting with prefix '20'.

    Structure:
    - Digits 0-1 (2 digits): Prefix '20'
    - Digits 2-6 (5 digits): Product SKU (e.g. '00123' or '123')
    - Digits 7-11 (5 digits): Weight in grams (e.g. '01500' = 1500g = 1.5kg)
    - Digit 12 (1 digit): Checksum digit
    """
    barcode = barcode.strip()
    if len(barcode) != 13 or not barcode.isdigit():
        return None

    if not barcode.startswith("20"):
        return None

    raw_sku_5 = barcode[2:7]
    raw_weight_5 = barcode[7:12]

    try:
        weight_grams = int(raw_weight_5)
    except ValueError:
        return None

    weight_kg = round(weight_grams / 1000.0, 3)

    return VariableWeightData(
        sku=raw_sku_5,
        weight_grams=weight_grams,
        weight_kg=weight_kg,
    )
