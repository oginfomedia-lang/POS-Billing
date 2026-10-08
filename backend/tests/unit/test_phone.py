"""Cleaning up and masking customer mobile numbers."""
import pytest

from app.errors.exceptions import AppError
from app.utils.phone import is_mobile, mask_mobile, normalize_mobile


@pytest.mark.parametrize("raw", ["9876543210", "+91 98765-43210", "919876543210", "09876543210", " 98765 43210 "])
def test_normalize_accepts_common_formats(raw):
    assert normalize_mobile(raw) == "9876543210"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_empty_means_no_mobile(raw):
    assert normalize_mobile(raw) is None


@pytest.mark.parametrize("raw", ["12345", "1234567890", "98765432101", "98765abcde", "5876543210"])
def test_invalid_numbers_are_rejected(raw):
    with pytest.raises(AppError):
        normalize_mobile(raw)
    assert is_mobile(raw) is False


def test_mask():
    assert mask_mobile("9876543210") == "98XXXXX210"
    assert mask_mobile(None) is None
