"""Unit tests for EAN-13 calculation, in-house generator, variable weight parser and barcode API services."""
import pytest
from decimal import Decimal

from app.errors.exceptions import ConflictError, NotFoundError
from app.models.enums import BarcodeType
from app.services import product_service
from app.utils.barcode_utils import (
    calculate_ean13_checksum,
    generate_inhouse_barcode,
    parse_scale_barcode,
    parse_variable_weight_barcode,
    validate_ean13,
)
from tests.factories import make_product, make_store


def test_ean13_checksum_calculation():
    # 290000000101 -> checksum is 5 -> 2900000001015
    checksum = calculate_ean13_checksum("290000000101")
    assert checksum == "5"
    assert validate_ean13("2900000001015") is True
    assert validate_ean13("2900000001019") is False


def test_inhouse_barcode_generation():
    code = generate_inhouse_barcode(101, prefix="290")
    assert len(code) == 13
    assert code.startswith("290000000101")
    assert validate_ean13(code) is True


def test_variable_weight_barcode_parsing():
    # 20 + 00123 (SKU) + 01500 (1500g = 1.5kg) + 0 (checksum placeholder)
    vw_code = "2000123015005"
    parsed = parse_variable_weight_barcode(vw_code)
    assert parsed is not None
    assert parsed.sku == "00123"
    assert parsed.weight_grams == 1500
    assert parsed.weight_kg == 1.5


@pytest.mark.parametrize("code, prefix, digits, expected", [
    ("2000123012505", "20", 5, ("123", 1250)),   # 20 + 00123 + 01250 + check
    ("2101230012504", "21", 4, ("123", 1250)),   # 21 + 0123 + 001250 + check
    ("2000012301255", "20", 6, ("123", 125)),    # 20 + 000123 + 0125 + check
    ("2000000012505", "20", 5, ("0", 1250)),
    ("2100123012505", "20", 5, None),            # other prefix
    ("200012301250", "20", 5, None),             # 12 digits
    ("20001230125A5", "20", 5, None),            # not all digits
])
def test_parse_scale_barcode(code, prefix, digits, expected):
    parsed = parse_scale_barcode(code, prefix, digits)
    assert (tuple(parsed) if parsed else None) == expected


def test_barcode_services_crud(app):
    with app.app_context():
        store = make_store()
        p = make_product(store, name="DMart Premia Almonds", price="500.00", sku="00123", is_variable_weight=True)

        # 1. Add barcode
        pb = product_service.add_product_barcode(p.id, "8901234567890", BarcodeType.MANUFACTURER)
        assert pb.barcode == "8901234567890"
        assert pb.barcode_type == BarcodeType.MANUFACTURER

        # 2. Prevent duplicate barcode
        with pytest.raises(ConflictError):
            product_service.add_product_barcode(p.id, "8901234567890")

        # 3. Generate in-house barcode
        inhouse_pb = product_service.generate_and_save_inhouse_barcode(p.id)
        assert inhouse_pb.barcode.startswith("290")
        assert inhouse_pb.barcode_type == BarcodeType.IN_HOUSE

        # 4. Scan variable weight barcode starting with '20'
        scan_res = product_service.scan_barcode("2000123015005")
        assert scan_res["is_variable_weight"] is True
        assert scan_res["weight_kg"] == 1.5
        assert scan_res["unit_price"] == Decimal("500.00")
        assert scan_res["calculated_price"] == Decimal("750.00")
        assert scan_res["product"].id == p.id

        # 5. Remove barcode
        product_service.remove_product_barcode(p.id, "8901234567890")
        with pytest.raises(NotFoundError):
            product_service.get_by_barcode("8901234567890")
