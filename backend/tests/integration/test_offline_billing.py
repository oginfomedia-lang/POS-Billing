"""Offline billing: the counter's catalogue, and uploading cash bills made while the server was unreachable."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.discount import Discount
from app.models.enums import DiscountScope, DiscountType, SaleStatus
from app.models.inventory import Inventory, StockBatch
from app.models.sale import Sale
from tests.factories import make_counter, make_product, make_shift, make_user

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store, code="C02"), opening_float="500.00")


def _bill(shift, product, qty="2", unit_price="10.00", tax_rate="5.00", discount="0.00", total=None, **extra):
    """An uploaded offline bill: line tax = (price × qty − discount) × rate, as the counter computes it."""
    line_total = (Decimal(unit_price) * Decimal(qty)).quantize(Decimal("0.01"))
    tax = ((line_total - Decimal(discount)) * Decimal(tax_rate) / 100).quantize(Decimal("0.01"))
    body = {
        "offline_id": str(uuid.uuid4()),
        "bill_number": "C02-OFF-261021-0001",
        "shift_id": shift.id,
        "billed_at": datetime.now(timezone.utc).isoformat(),
        "items": [{
            "product_id": product.id, "product_name": product.name, "qty": qty, "unit_price": unit_price,
            "tax_rate": tax_rate, "discount_amount": discount, "offer_discount": discount,
        }],
        "total": total or str(line_total - Decimal(discount) + tax),
        "cash_tendered": "500",
    }
    body.update(extra)
    return body


def _stock(store, product):
    db.session.expire_all()
    return db.session.scalar(db.select(Inventory.qty_on_hand).where(
        Inventory.store_id == store.id, Inventory.product_id == product.id))


def test_catalog_has_store_prices_offers_and_receipt_details(client, cashier_headers, store):
    tea = make_product(store, name="Tea", price="100.00", barcode="8900000000011")
    db.session.scalar(db.select(Inventory).where(Inventory.product_id == tea.id)).price = Decimal("95.00")
    db.session.add(Discount(name="10% tea", discount_type=DiscountType.PERCENTAGE, value=10,
                            scope=DiscountScope.PRODUCT, product_id=tea.id))
    db.session.add(Discount(name="Over", discount_type=DiscountType.FIXED, value=5, scope=DiscountScope.BILL,
                            ends_at=datetime.now(timezone.utc) - timedelta(days=1)))
    db.session.commit()

    resp = client.get("/api/v1/pos/offline-catalog", query_string={"store_id": store.id}, headers=cashier_headers)
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    product = next(p for p in body["products"] if p["id"] == tea.id)
    assert (product["price"], product["barcode"]) == ("95.00", "8900000000011")
    assert [o["name"] for o in body["offers"]] == ["10% tea"]  # ended offers are left out
    assert body["store"]["name"] == store.name and "receipt_footer" in body["settings"]


def test_offline_bill_is_recorded_paid_with_stock_taken(client, cashier_headers, cashier_user, shift, store):
    soap = make_product(store, name="Soap", stock=10)
    resp = client.post("/api/v1/sales/offline", json=_bill(shift, soap, qty="3"), headers=cashier_headers)
    assert resp.status_code == 201, resp.get_json()
    sale = resp.get_json()
    assert (sale["status"], sale["bill_number"], sale["total"]) == ("paid", "C02-OFF-261021-0001", "31.50")
    assert sale["payments"][0]["change_due"] == "468.50"
    assert _stock(store, soap) == Decimal("7")
    assert db.session.scalar(db.select(db.func.sum(StockBatch.qty_remaining)).where(
        StockBatch.product_id == soap.id)) == Decimal("7")


def test_uploading_the_same_bill_twice_records_it_once(client, cashier_headers, shift, store):
    soap = make_product(store, name="Soap", stock=10)
    body = _bill(shift, soap)
    assert client.post("/api/v1/sales/offline", json=body, headers=cashier_headers).status_code == 201
    again = client.post("/api/v1/sales/offline", json=body, headers=cashier_headers)
    assert again.status_code == 200
    assert db.session.scalar(db.select(db.func.count(Sale.id)).where(Sale.status == SaleStatus.PAID)) == 1
    assert _stock(store, soap) == Decimal("8")


def test_totals_that_dont_add_up_are_refused(client, cashier_headers, shift, store):
    soap = make_product(store, name="Soap", stock=10)
    resp = client.post("/api/v1/sales/offline", json=_bill(shift, soap, total="20.00"), headers=cashier_headers)
    assert resp.status_code == 400
    assert resp.get_json()["error"]["details"]["expected_total"] == "21.00"
    assert _stock(store, soap) == Decimal("10")


def test_discount_is_kept_as_charged(client, cashier_headers, shift, store):
    oil = make_product(store, name="Oil", stock=5)
    body = _bill(shift, oil)
    body["items"] = [{"product_id": oil.id, "product_name": "Oil", "qty": "2", "unit_price": "100.00",
                      "tax_rate": "5.00", "discount_amount": "20.00", "offer_id": None, "offer_name": "10% off",
                      "offer_discount": "20.00"}]
    body["total"] = "189.00"  # 200 − 20 + 5% of 180
    resp = client.post("/api/v1/sales/offline", json=body, headers=cashier_headers)
    assert resp.status_code == 201, resp.get_json()
    item = resp.get_json()["items"][0]
    assert (item["discount_amount"], item["tax_amount"], item["offer_name"]) == ("20.00", "9.00", "10% off")


def test_overselling_offline_takes_stock_to_zero_and_is_noted(client, cashier_headers, shift, store):
    milk = make_product(store, name="Milk", stock=1)
    resp = client.post("/api/v1/sales/offline", json=_bill(shift, milk, qty="3"), headers=cashier_headers)
    assert resp.status_code == 201
    assert _stock(store, milk) == Decimal("0")
    log = db.session.scalar(db.select(AuditLog).where(AuditLog.action == "sale.offline"))
    assert log.new_values["stock_short"][0]["product_name"] == "Milk"


def test_another_cashiers_shift_is_refused(client, store, shift):
    other = make_user(role="cashier", username="other", pin="2468", store=store)
    token = client.post("/api/v1/auth/login", json={"username": "other", "pin": "2468"}).get_json()["access_token"]
    soap = make_product(store, name="Soap", stock=10)
    resp = client.post("/api/v1/sales/offline", json=_bill(shift, soap),
                       headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_bill_dated_in_the_future_is_refused(client, cashier_headers, shift, store):
    soap = make_product(store, name="Soap", stock=10)
    body = _bill(shift, soap, billed_at=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat())
    assert client.post("/api/v1/sales/offline", json=body, headers=cashier_headers).status_code == 400


def test_offline_bill_shows_in_the_shift(client, cashier_headers, shift, store):
    soap = make_product(store, name="Soap", stock=10)
    client.post("/api/v1/sales/offline", json=_bill(shift, soap), headers=cashier_headers)
    bills = client.get(f"/api/v1/shifts/{shift.id}/bills", headers=cashier_headers).get_json()
    numbers = [b["bill_number"] for b in (bills["bills"] if isinstance(bills, dict) else bills)]
    assert "C02-OFF-261021-0001" in numbers
