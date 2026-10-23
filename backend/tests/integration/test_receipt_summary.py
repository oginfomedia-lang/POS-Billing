"""Receipt summary under the items: number of bill lines and the sum of their quantities, from the saved bill."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import ebill_pdf, receipt_service
from tests.factories import make_counter, make_product, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def _add(client, headers, sid, product, qty):
    resp = client.post(f"/api/v1/sales/{sid}/items", json={"product_id": product.id, "qty": qty}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def test_summary_counts_merged_lines_and_sums_quantities(client, cashier_headers, shift, store):
    bisc = make_product(store, name="Good Day", price="30.00", tax_rate="0.00")
    milk = make_product(store, name="Milk", price="28.00", tax_rate="0.00")
    soap = make_product(store, name="Soap", price="25.00", tax_rate="0.00")
    rice = make_product(store, name="Rice loose", price="70.00", tax_rate="0.00", is_variable_weight=True)

    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    _add(client, cashier_headers, sid, bisc, 1)
    _add(client, cashier_headers, sid, bisc, 1)  # scanned again: same line, qty 2
    _add(client, cashier_headers, sid, milk, 3)
    sale = _add(client, cashier_headers, sid, soap, 4)
    soap_line = next(i for i in sale["items"] if i["product_name"] == "Soap")
    client.delete(f"/api/v1/sales/{sid}/items/{soap_line['id']}", headers=cashier_headers)  # removed: not counted
    _add(client, cashier_headers, sid, rice, "1.25")
    paid = client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "1000"},
                       headers=cashier_headers).get_json()

    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert len(receipt["items"]) == 3
    assert (receipt["item_lines"], receipt["total_qty"]) == (3, "6")  # 2 + 3 + 1 (1.25 kg loose rice counts as 1)
    # The summary changes nothing else on the bill.
    assert receipt["total"] == paid["total"] == "231.50"  # 60 + 84 + 87.50


def test_total_qty_is_exact_and_tidy():
    lines = lambda *q: [SimpleNamespace(qty=Decimal(x)) for x in q]  # noqa: E731
    assert str(receipt_service.total_qty(lines("2", "3", "1", "4"))) == "10"
    assert str(receipt_service.total_qty(lines("1.000", "3.500", "19.000"))) == "23.5"
    assert str(receipt_service.total_qty(lines("0.1", "0.2", "0.235"))) == "0.535"  # no float drift
    assert str(receipt_service.total_qty([])) == "0"
    # 1.5 kg loose sugar + 1 KitKat = 2 items.
    sugar = SimpleNamespace(qty=Decimal("1.500"), is_variable_weight=True)
    kitkat = SimpleNamespace(qty=Decimal("1"), is_variable_weight=False)
    assert str(receipt_service.total_qty([sugar, kitkat])) == "2"


def test_ebill_pdf_has_the_same_summary(client, cashier_headers, shift, store):
    p = make_product(store, name="Milk", price="28.00", tax_rate="0.00")
    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    _add(client, cashier_headers, sid, p, 3)
    client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "100"}, headers=cashier_headers)

    receipt = receipt_service.build_receipt(sid)
    assert ebill_pdf.item_summary(receipt) == ("Total Items: 1", "Total Qty: 3")
    assert ebill_pdf.render(receipt).startswith(b"%PDF")
