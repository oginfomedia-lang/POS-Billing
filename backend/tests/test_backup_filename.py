"""Backup filenames carry the shop: pos_<shop-code>_<UTC date>_<UTC time>.pgdump."""
import re

from app.models.store import Store
from app.services import backup_service, license_service
from app.services.license_service import LicenseStatus


def test_shop_code_from_first_store(app, store, monkeypatch):
    monkeypatch.setattr(license_service, "current_status",
                        lambda: LicenseStatus(False, "abcdef1234567890", "not_activated"))
    monkeypatch.setattr(license_service, "machine_id", lambda: "abcdef1234567890")
    store.name = "Sharma Mart & Sons"
    assert backup_service.shop_code() == "sharma-mart-sons-abcdef"


def test_shop_code_prefers_licensed_customer(app, store, monkeypatch):
    monkeypatch.setattr(license_service, "current_status",
                        lambda: LicenseStatus(True, "abcdef1234567890", customer_name="Gupta Kirana"))
    monkeypatch.setattr(license_service, "machine_id", lambda: "abcdef1234567890")
    assert backup_service.shop_code() == "gupta-kirana-abcdef"


def test_shop_code_without_ascii_name(app, monkeypatch):
    monkeypatch.setattr(license_service, "current_status",
                        lambda: LicenseStatus(False, "abcdef1234567890", "not_activated"))
    monkeypatch.setattr(license_service, "machine_id", lambda: "abcdef1234567890")
    from app.extensions import db

    db.session.add(Store(name="शर्मा मार्ट"))
    db.session.flush()
    assert backup_service.shop_code() == "shop-abcdef"
    assert re.fullmatch(r"[a-z0-9-]+", backup_service.shop_code())
