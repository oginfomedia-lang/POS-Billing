"""Products page → Export (Excel / CSV): same columns as the import template, so the file imports back."""
import csv
import io
from decimal import Decimal

import pytest
from openpyxl import load_workbook

from app.extensions import db
from app.models.product import Product
from app.services.product_export_service import HEADER
from tests.factories import make_product

pytestmark = pytest.mark.integration
URL = "/api/v1/products/export"


def _sheet(resp):
    ws = load_workbook(io.BytesIO(resp.data))["Products"]
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    return ws, rows[0], {r[0]: dict(zip(rows[0], r)) for r in rows[1:]}


def test_excel_has_every_product_with_the_import_columns(client, admin_headers, store):
    p = make_product(store, name="Tata Salt 1kg", price="26.00", tax_rate="5", mrp="28.00",
                     barcode="8901058000017", hsn_code="2501")
    p.cost_price = Decimal("22")
    for i in range(30):  # more than one page of the Products screen (25)
        make_product(store, name=f"Item {i:02d}")
    db.session.commit()

    resp = client.get(URL, headers=admin_headers)
    assert resp.status_code == 200 and "spreadsheetml" in resp.content_type
    ws, header, rows = _sheet(resp)
    assert header == HEADER
    assert len(rows) == 31
    salt = rows["Tata Salt 1kg"]
    assert salt["barcodes"] == "8901058000017"  # text: Excel shows all 13 digits, not 8.90106E+12
    assert (salt["price"], salt["tax_rate"], salt["mrp"], salt["cost_price"]) == (26, 5, 28, 22)
    assert salt["price_with_gst"] == 27.3 and salt["active"] == "yes"
    assert ws["I2"].number_format == "@"


def test_csv_follows_the_filters_and_hides_cost_from_cashiers(client, admin_headers, cashier_headers, store):
    make_product(store, name="Parle-G 100g", price="9.50").cost_price = Decimal("8.20")
    make_product(store, name="Old soap").is_active = False
    db.session.commit()

    resp = client.get(URL, query_string={"format": "csv", "status": "active"}, headers=admin_headers)
    assert resp.status_code == 200 and resp.content_type.startswith("text/csv")
    assert resp.data.startswith("﻿".encode())  # Excel reads Marathi / ₹ right
    rows = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8-sig"))))
    assert [(r["name"], r["cost_price"]) for r in rows] == [("Parle-G 100g", "8.2000")]

    resp = client.get(URL, query_string={"format": "csv", "q": "parle"}, headers=cashier_headers)
    assert resp.status_code == 200  # cashiers may read products, but never see the purchase cost
    rows = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8-sig"))))
    assert rows and all(r["cost_price"] == "" for r in rows)


def test_a_name_starting_with_equals_is_never_a_formula(client, admin_headers, store):
    make_product(store, name="=HYPERLINK(\"http://x\")")
    ws, _, _ = _sheet(client.get(URL, headers=admin_headers))
    assert ws["A2"].data_type == "s"
    text = client.get(URL, query_string={"format": "csv"}, headers=admin_headers).data.decode("utf-8-sig")
    assert "'=HYPERLINK" in text


def test_exported_file_imports_back_as_updates(client, admin_headers, store):
    make_product(store, name="Tata Salt 1kg", price="26.00", sku="SALT-1")
    exported = client.get(URL, headers=admin_headers).data
    wb = load_workbook(io.BytesIO(exported))
    ws = wb["Products"]
    ws.cell(row=2, column=HEADER.index("price") + 1, value=27)  # the shop changes the price in Excel
    changed = io.BytesIO()
    wb.save(changed)

    resp = client.post("/api/v1/products/import", headers=admin_headers, content_type="multipart/form-data",
                       data={"file": (io.BytesIO(changed.getvalue()), "products.xlsx"), "store_id": str(store.id)})
    assert resp.status_code == 201, resp.get_json()
    db.session.expire_all()
    assert db.session.scalar(db.select(Product).filter_by(sku="SALT-1")).price == Decimal("27.00")
    assert db.session.scalar(db.select(db.func.count()).select_from(Product)) == 1  # updated, not duplicated


def test_bad_format(client, admin_headers):
    assert client.get(URL, query_string={"format": "pdf"}, headers=admin_headers).status_code == 400
