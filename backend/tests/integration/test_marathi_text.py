"""Marathi (Devanagari) names typed with the phonetic keyboard are saved, found and printed unchanged."""
import pytest

from app.services import ebill_pdf, receipt_service
from tests.factories import make_counter, make_shift

pytestmark = pytest.mark.integration


@pytest.fixture
def shift(cashier_user, store):
    return make_shift(cashier_user, make_counter(store))


def test_marathi_names_round_trip_search_and_print(client, admin_headers, cashier_headers, shift, store):
    cat = client.post("/api/v1/categories", json={"name": "किराणा"}, headers=admin_headers)
    assert cat.status_code == 201 and cat.get_json()["name"] == "किराणा"
    # Same name again is a duplicate (Devanagari has no letter case; the check still works).
    assert client.post("/api/v1/categories", json={"name": " किराणा "}, headers=admin_headers).status_code == 409

    sup = client.post("/api/v1/suppliers", json={
        "company_name": "श्री गणेश ट्रेडर्स", "contact_person": "रमेश पाटील", "billing_address": "पुणे रोड, पंढरपूर",
    }, headers=admin_headers)
    assert sup.status_code == 201, sup.get_json()
    assert (sup.get_json()["company_name"], sup.get_json()["contact_person"]) == ("श्री गणेश ट्रेडर्स", "रमेश पाटील")

    prod = client.post("/api/v1/products", json={
        "name": "साखर 1 किलो", "price": "45", "category_id": cat.get_json()["id"], "store_id": store.id,
    }, headers=admin_headers)
    assert prod.status_code == 201 and prod.get_json()["name"] == "साखर 1 किलो"
    pid = prod.get_json()["id"]
    client.post("/api/v1/inventory/stock-in", json={"store_id": store.id, "product_id": pid, "qty": "10", "notes": "QA"},
                headers=admin_headers)

    # Found by a part of the Marathi name.
    found = client.get("/api/v1/products", query_string={"q": "साख"}, headers=admin_headers).get_json()["items"]
    assert [p["name"] for p in found] == ["साखर 1 किलो"]

    # Billed and printed with the Devanagari name.
    sid = client.post("/api/v1/sales", headers=cashier_headers).get_json()["id"]
    client.post(f"/api/v1/sales/{sid}/items", json={"product_id": pid, "qty": 2}, headers=cashier_headers)
    client.post(f"/api/v1/sales/{sid}/complete", json={"method": "cash", "cash_tendered": "100"}, headers=cashier_headers)
    receipt = client.get(f"/api/v1/sales/{sid}/receipt", headers=cashier_headers).get_json()
    assert receipt["items"][0]["product_name"] == "साखर 1 किलो"
    assert ebill_pdf.render(receipt_service.build_receipt(sid)).startswith(b"%PDF")


def test_marathi_store_and_staff_names(client, admin_headers, store):
    s = client.post("/api/v1/stores", json={"name": "सुपर बझार", "address": "पुणे रोड, पंढरपूर"}, headers=admin_headers)
    assert s.status_code == 201 and s.get_json()["name"] == "सुपर बझार"
    u = client.post("/api/v1/users", json={"username": "nilesh", "full_name": "निलेश", "pin": "2468", "role": "cashier",
                                          "store_id": s.get_json()["id"]}, headers=admin_headers)
    assert u.status_code == 201 and u.get_json()["full_name"] == "निलेश"
